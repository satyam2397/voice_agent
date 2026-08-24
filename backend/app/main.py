import asyncio
import json
import logging
import time
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from app.config import settings
from app.orchestrator.agent import Agent
from app.orchestrator.llm_client import get_llm_client
from app.orchestrator.tool_registry import ToolRegistry
from app.orchestrator.trigger_classifier import TriggerClassifier
from app.session import ConversationSession
from app.stt import DeepgramStream, Transcript

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("sales_copilot.audio")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Connect the MCP tools once for the process lifetime.

    Per-request connection would put tool discovery inside the latency budget
    for every single flash card.
    """
    registry = ToolRegistry()
    try:
        await registry.connect()
    except Exception:
        log.exception("tool_registry_connect_failed — running without tools")

    app.state.tools = registry

    # A missing or misconfigured LLM must not stop the server booting —
    # transcription is independently useful, and the UI reports what is off.
    app.state.agent = None
    ok, why = _llm_available()
    if ok:
        try:
            app.state.agent = Agent(get_llm_client(), registry)
            log.info(
                "agent_ready provider=%s model=%s",
                settings.llm_provider,
                settings.anthropic_model
                if settings.llm_provider == "anthropic"
                else settings.ollama_model,
            )
        except Exception as exc:
            log.warning("llm_client_init_failed error=%s", exc)
    else:
        log.warning("no LLM: %s — transcription works, flash cards will not", why)

    yield
    await registry.close()


def _llm_available() -> tuple[bool, str]:
    """Check config *and* that the client library is actually installed."""
    import importlib.util

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            return False, "ANTHROPIC_API_KEY is empty"
        if importlib.util.find_spec("anthropic") is None:
            return False, "anthropic package not installed"
        return True, ""

    if importlib.util.find_spec("ollama") is None:
        return False, "ollama package not installed"
    return True, ""


app = FastAPI(title="Sales Co-Pilot", lifespan=lifespan)

# Vite proxies /ws during development, so requests are same-origin. This is here
# for the case where the frontend is served from a different port directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATS_INTERVAL_S = 1.0

# Expected wire format from the AudioWorklet.
EXPECTED_ENCODING = "pcm_s16le"
EXPECTED_SAMPLE_RATE = 16_000


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "stt_configured": bool(settings.deepgram_api_key),
        "stt_model": settings.deepgram_model,
        # Listing what was actually loaded makes "my key isn't picked up"
        # a two-second diagnosis instead of a guess.
        "env_files_loaded": settings.env_files_loaded,
        "llm_provider": settings.llm_provider,
        "llm_ready": getattr(app.state, "agent", None) is not None,
        "llm_issue": _llm_available()[1] or None,
        "tools": [s["name"] for s in getattr(app.state, "tools", None).schemas()]
        if getattr(app.state, "tools", None)
        else [],
    }


@app.get("/api/distributors")
async def list_distributors():
    """Who the rep can pick from before starting a meeting."""
    from sqlalchemy import select

    from app.db.models import Distributor
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        rows = session.scalars(select(Distributor).order_by(Distributor.name))
        return [
            {
                "id": str(d.id),
                "name": d.name,
                "region": d.region,
                "aum_tier": d.aum_tier,
                "risk_appetite": d.risk_appetite,
            }
            for d in rows
        ]
    except Exception:
        log.exception("distributor_list_failed")
        return []
    finally:
        session.close()


@app.websocket("/ws/audio/{conversation_id}")
async def audio_stream(websocket: WebSocket, conversation_id: str):
    """
    Receives the live mic stream for one conversation and streams back
    transcripts.

    One device captures both people at the table, so this is a single mixed
    stream. Speaker separation is Deepgram's diarization; mapping those labels
    onto rep/distributor is one tap from the rep.

    Protocol:
      client -> server : JSON handshake, then raw PCM16 @16kHz binary frames
      client -> server : JSON control messages (role assignment)
      server -> client : JSON events (ready, transcript, role_prompt, stats, error)
    """
    await websocket.accept()

    session = ConversationSession(conversation_id=conversation_id)
    trigger = TriggerClassifier()
    agent: Agent | None = getattr(app.state, "agent", None)
    send_lock = asyncio.Lock()
    agent_tasks: set[asyncio.Task] = set()

    bytes_received = 0
    chunks_received = 0
    started_at = time.monotonic()
    last_stats_at = started_at

    async def send(payload: dict) -> None:
        """Serialize sends — the STT reader task and the audio loop share this socket."""
        async with send_lock:
            try:
                await websocket.send_json(payload)
            except Exception:
                pass

    async def run_agent(conversation: str, reason: str) -> None:
        """Produce a flash card. Runs detached so audio ingestion never blocks."""
        assert agent is not None
        result = await agent.run(
            conversation=conversation,
            trigger_reason=reason,
            distributor_id=session.distributor_id,
        )

        log.info(
            "agent_done reason=%s tools=%s tokens=%d/%d latency=%dms error=%s",
            reason,
            [t["tool"] for t in result.tool_calls],
            result.input_tokens,
            result.output_tokens,
            result.latency_ms,
            result.error,
        )

        if not result.content:
            # Fail closed: no card beats a made-up one.
            await send(
                {
                    "type": "card_skipped",
                    "reason": result.error or "no_content",
                    "latency_ms": result.latency_ms,
                }
            )
            return

        await send(
            {
                "type": "flash_card",
                "id": str(uuid.uuid4()),
                "content": result.content,
                "trigger_reason": reason,
                "category": None,
                "latency_ms": result.latency_ms,
                "tools_used": [t["tool"] for t in result.tool_calls],
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            }
        )

    async def on_transcript(t: Transcript) -> None:
        speaker = session.role_for(t.speaker_tag)

        if t.is_final:
            session.note_speaker(t.speaker_tag, t.text)

        await send(
            {
                "type": "transcript",
                "id": str(uuid.uuid4()),
                "speaker": speaker,
                "speaker_tag": t.speaker_tag,
                "text": t.text,
                "is_final": t.is_final,
                "confidence": t.confidence,
                "start": t.start,
                "end": t.end,
            }
        )

        # Ask who is who the moment we can actually distinguish two voices.
        if session.should_prompt_for_roles():
            session.prompted = True
            await send(
                {"type": "role_prompt", "speakers": session.speaker_options()}
            )

        if not t.is_final:
            return

        session.add_turn(speaker, t.text)

        decision = trigger.classify(speaker=speaker, text=t.text)
        await send(
            {
                "type": "trigger",
                "triggered": decision.triggered,
                "reason": decision.reason,
                "confidence": decision.confidence,
            }
        )
        if not decision.triggered:
            return

        if agent is None or not session.distributor_id:
            await send(
                {
                    "type": "card_skipped",
                    "reason": "no_llm" if agent is None else "no_distributor_selected",
                    "latency_ms": 0,
                }
            )
            return

        trigger.note_fired()
        # Detached: a 2s agent run must not stall the audio loop.
        task = asyncio.create_task(run_agent(session.window(), decision.reason))
        agent_tasks.add(task)
        task.add_done_callback(agent_tasks.discard)

    async def on_stt_error(message: str) -> None:
        await send({"type": "error", "message": message})

    stt = DeepgramStream(
        settings.deepgram_api_key,
        on_transcript=on_transcript,
        on_error=on_stt_error,
        sample_rate=EXPECTED_SAMPLE_RATE,
        model=settings.deepgram_model,
    )

    try:
        # --- handshake ---------------------------------------------------
        raw = await websocket.receive_text()
        try:
            handshake = json.loads(raw)
        except json.JSONDecodeError:
            await send({"type": "error", "message": "First frame must be JSON handshake"})
            await websocket.close(code=1003)
            return

        encoding = handshake.get("encoding")
        sample_rate = handshake.get("sample_rate")
        if encoding != EXPECTED_ENCODING or sample_rate != EXPECTED_SAMPLE_RATE:
            await send(
                {
                    "type": "error",
                    "message": (
                        f"Expected {EXPECTED_ENCODING} @ {EXPECTED_SAMPLE_RATE} Hz, "
                        f"got {encoding} @ {sample_rate}"
                    ),
                }
            )
            await websocket.close(code=1003)
            return

        # Who the rep is meeting. Chosen in the UI before recording starts;
        # this is the only tenant scope tool calls will ever use.
        session.distributor_id = str(handshake.get("distributor_id") or "")

        log.info(
            "stream_open conversation_id=%s distributor_id=%s encoding=%s sample_rate=%s",
            conversation_id,
            session.distributor_id or "(none)",
            encoding,
            sample_rate,
        )

        # Transcription failing is not fatal — we keep ingesting audio and the
        # UI shows why it is silent (DESIGN.md §9, failure mode 5).
        transcribing = await stt.start()
        await send(
            {
                "type": "ready",
                "conversation_id": conversation_id,
                "transcribing": transcribing,
                "agent_enabled": agent is not None and bool(session.distributor_id),
            }
        )

        # --- frames ------------------------------------------------------
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            # Control messages arrive as text on the same socket.
            if (text := message.get("text")) is not None:
                await _handle_control(text, session, send)
                continue

            payload = message.get("bytes")
            if payload is None:
                continue

            bytes_received += len(payload)
            chunks_received += 1

            # TODO(phase 2): Silero VAD here, so silence never reaches Deepgram.
            await stt.send_audio(payload)

            now = time.monotonic()
            if now - last_stats_at >= STATS_INTERVAL_S:
                last_stats_at = now
                await send(
                    {
                        "type": "stats",
                        "bytes_received": bytes_received,
                        "chunks_received": chunks_received,
                    }
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("stream_error conversation_id=%s", conversation_id)
    finally:
        await stt.close()
        # Let in-flight cards finish rather than cancelling mid-tool-call.
        if agent_tasks:
            await asyncio.wait(agent_tasks, timeout=5)
        duration = time.monotonic() - started_at
        expected = duration * EXPECTED_SAMPLE_RATE * 2  # 16-bit mono
        log.info(
            "stream_close conversation_id=%s duration=%.1fs chunks=%d bytes=%d "
            "capture_ratio=%.2f speakers=%d roles=%s",
            conversation_id,
            duration,
            chunks_received,
            bytes_received,
            (bytes_received / expected) if expected else 0.0,
            len(session.samples),
            session.roles or "unassigned",
        )


async def _handle_control(text: str, session: ConversationSession, send) -> None:
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        return

    if message.get("type") == "assign_role":
        rep_tag = message.get("rep_tag")
        if isinstance(rep_tag, int):
            session.assign(rep_tag)
            log.info("roles_assigned rep_tag=%s roles=%s", rep_tag, session.roles)
            await send({"type": "roles_assigned", "roles": session.roles})
