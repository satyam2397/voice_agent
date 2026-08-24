"""
Streaming speech-to-text via Deepgram.

Single provider by design (see DESIGN.md §5): once speaker separation has to be
inferred from one mixed microphone, diarization stops being a nice-to-have and
becomes the thing the pipeline rests on. A self-hosted path that cannot diarize
would not be a real alternative.

Talks to Deepgram over a raw WebSocket rather than the official SDK — one fewer
dependency, no SDK version churn, and every frame on the wire is inspectable.

Everything Deepgram-specific lives in this module. Swapping providers later
means rewriting this file, not touching the pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urlencode

import certifi
import websockets

log = logging.getLogger("sales_copilot.stt")

DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"


def _build_ssl_context() -> ssl.SSLContext:
    """
    Prefer the operating system's trust store, fall back to certifi.

    Networks running TLS inspection (Zscaler, Netskope, most corporate proxies)
    re-sign every certificate with a private root. That root is installed in the
    OS trust store — which is why browsers work — but Python ships its own CA
    bundle and never consults the OS, so the same request fails with
    CERTIFICATE_VERIFY_FAILED.

    `truststore` bridges that gap. Certificate verification stays fully enabled;
    we are supplying the correct roots, not skipping the check.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        log.info("truststore unavailable, using certifi CA bundle")
        return ssl.create_default_context(cafile=certifi.where())


_SSL_CONTEXT = _build_ssl_context()

# Deepgram closes an idle socket after ~10s. Audio normally flows continuously,
# but once VAD lands (Phase 2) we will be withholding silence, so keep the
# connection warm explicitly.
KEEPALIVE_INTERVAL_S = 5.0


@dataclass(frozen=True)
class Transcript:
    """One utterance fragment attributed to a single diarized speaker."""

    text: str
    speaker_tag: int | None
    is_final: bool
    confidence: float | None
    start: float
    end: float


TranscriptHandler = Callable[[Transcript], Awaitable[None]]
ErrorHandler = Callable[[str], Awaitable[None]]


def _build_url(sample_rate: int, model: str, language: str) -> str:
    params = {
        "model": model,
        "language": language,
        "encoding": "linear16",
        "sample_rate": str(sample_rate),
        "channels": "1",
        # One mic, two people — diarization is the whole reason this works.
        "diarize": "true",
        # Partials drive the live UI only; nothing downstream consumes them.
        "interim_results": "true",
        "punctuate": "true",
        "smart_format": "true",
        # Silence (ms) before Deepgram finalises a segment. Lower = snappier
        # turns, more fragmentation. 300ms is a reasonable conversational value.
        "endpointing": "300",
        "utterance_end_ms": "1000",
    }
    return f"{DEEPGRAM_URL}?{urlencode(params)}"


class DeepgramStream:
    """
    A single live transcription session.

    Usage:
        stream = DeepgramStream(api_key, on_transcript=..., on_error=...)
        await stream.start()
        await stream.send_audio(pcm_bytes)   # repeatedly
        await stream.close()

    Failure is non-fatal by design (DESIGN.md §9, failure mode 5): if Deepgram
    is unreachable or drops, `send_audio` becomes a no-op and the caller keeps
    ingesting audio rather than tearing the conversation down.
    """

    def __init__(
        self,
        api_key: str,
        *,
        on_transcript: TranscriptHandler,
        on_error: ErrorHandler,
        sample_rate: int = 16_000,
        model: str = "nova-3",
        language: str = "en",
    ) -> None:
        self._api_key = api_key
        self._on_transcript = on_transcript
        self._on_error = on_error
        self._url = _build_url(sample_rate, model, language)

        self._socket: websockets.ClientConnection | None = None
        self._reader: asyncio.Task[None] | None = None
        self._keepalive: asyncio.Task[None] | None = None
        self._closing = False

    @property
    def is_live(self) -> bool:
        return self._socket is not None and not self._closing

    async def start(self) -> bool:
        """Open the upstream socket. Returns False if it could not connect."""
        if not self._api_key:
            await self._on_error(
                "DEEPGRAM_API_KEY is not set — transcription disabled. "
                "Add it to backend/.env and restart."
            )
            return False

        try:
            self._socket = await websockets.connect(
                self._url,
                additional_headers={"Authorization": f"Token {self._api_key}"},
                ssl=_SSL_CONTEXT,
                max_size=None,
            )
        except Exception as exc:
            log.warning("deepgram_connect_failed error=%s", exc)
            await self._on_error(f"Could not reach Deepgram: {exc}")
            return False

        self._reader = asyncio.create_task(self._read_loop())
        self._keepalive = asyncio.create_task(self._keepalive_loop())
        log.info("deepgram_connected")
        return True

    async def send_audio(self, pcm: bytes) -> None:
        if self._socket is None or self._closing:
            return
        try:
            await self._socket.send(pcm)
        except Exception as exc:
            log.warning("deepgram_send_failed error=%s", exc)
            self._socket = None
            await self._on_error("Transcription stream dropped.")

    async def close(self) -> None:
        self._closing = True

        if self._socket is not None:
            try:
                # Tells Deepgram to flush and finalise rather than truncate.
                await self._socket.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass

        for task in (self._keepalive, self._reader):
            if task is not None:
                task.cancel()

        if self._socket is not None:
            try:
                await self._socket.close()
            except Exception:
                pass
            self._socket = None

        log.info("deepgram_closed")

    # ---------------- internals ----------------

    async def _keepalive_loop(self) -> None:
        try:
            while not self._closing and self._socket is not None:
                await asyncio.sleep(KEEPALIVE_INTERVAL_S)
                if self._socket is None:
                    return
                await self._socket.send(json.dumps({"type": "KeepAlive"}))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _read_loop(self) -> None:
        assert self._socket is not None
        try:
            async for raw in self._socket:
                if not isinstance(raw, str):
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._handle(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closing:
                log.warning("deepgram_read_failed error=%s", exc)
                await self._on_error("Transcription stream ended unexpectedly.")

    async def _handle(self, payload: dict) -> None:
        kind = payload.get("type")

        if kind == "Error":
            message = payload.get("description") or payload.get("message") or "unknown"
            log.warning("deepgram_error %s", message)
            await self._on_error(f"Deepgram error: {message}")
            return

        if kind != "Results":
            # Metadata / SpeechStarted / UtteranceEnd — not needed yet.
            return

        alternatives = payload.get("channel", {}).get("alternatives", [])
        if not alternatives:
            return

        best = alternatives[0]
        if not (best.get("transcript") or "").strip():
            return

        is_final = bool(payload.get("is_final"))
        base_start = float(payload.get("start", 0.0))
        duration = float(payload.get("duration", 0.0))
        words = best.get("words") or []

        if not words:
            # Interim results often arrive before word-level detail exists.
            await self._on_transcript(
                Transcript(
                    text=best["transcript"].strip(),
                    speaker_tag=None,
                    is_final=is_final,
                    confidence=best.get("confidence"),
                    start=base_start,
                    end=base_start + duration,
                )
            )
            return

        for fragment in _split_by_speaker(words):
            await self._on_transcript(
                Transcript(
                    text=fragment["text"],
                    speaker_tag=fragment["speaker"],
                    is_final=is_final,
                    confidence=fragment["confidence"],
                    start=fragment["start"],
                    end=fragment["end"],
                )
            )


def _split_by_speaker(words: list[dict]) -> list[dict]:
    """
    Group consecutive words by diarized speaker.

    A single Deepgram result can contain more than one speaker when people talk
    over each other — which happens constantly in an in-person meeting. Emitting
    the whole thing as one turn would attribute the interruption to whoever
    started speaking first.
    """
    groups: list[dict] = []

    for word in words:
        speaker = word.get("speaker")
        text = word.get("punctuated_word") or word.get("word") or ""
        if not text:
            continue

        if groups and groups[-1]["speaker"] == speaker:
            current = groups[-1]
            current["parts"].append(text)
            current["end"] = float(word.get("end", current["end"]))
            current["confidences"].append(float(word.get("confidence", 1.0)))
        else:
            groups.append(
                {
                    "speaker": speaker,
                    "parts": [text],
                    "start": float(word.get("start", 0.0)),
                    "end": float(word.get("end", 0.0)),
                    "confidences": [float(word.get("confidence", 1.0))],
                }
            )

    return [
        {
            "speaker": g["speaker"],
            "text": " ".join(g["parts"]).strip(),
            "start": g["start"],
            "end": g["end"],
            "confidence": (
                sum(g["confidences"]) / len(g["confidences"]) if g["confidences"] else None
            ),
        }
        for g in groups
    ]
