"""Simulates the browser AudioWorklet: handshake, then PCM16 @16kHz frames."""
import asyncio
import json
import math
import struct
import sys

import websockets

URL = "ws://localhost:8000/ws/audio/smoke-test-conversation"
SAMPLE_RATE = 16000
CHUNK_MS = 200
SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000  # 3200
CHUNKS = 15  # 3 seconds


def tone_chunk(i: int) -> bytes:
    """440 Hz sine, same shape the worklet emits."""
    base = i * SAMPLES
    return struct.pack(
        f"<{SAMPLES}h",
        *[
            int(0.3 * 32767 * math.sin(2 * math.pi * 440 * (base + n) / SAMPLE_RATE))
            for n in range(SAMPLES)
        ],
    )


async def main() -> int:
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({
            "type": "start",
            "sample_rate": SAMPLE_RATE,
            "encoding": "pcm_s16le",
            "channels": 1,
        }))

        # `ready` may be preceded by an error frame — e.g. no DEEPGRAM_API_KEY.
        # That is the designed behaviour: transcription is optional, audio
        # ingestion is not. Drain until we see `ready`.
        ready = None
        preamble = []
        while ready is None:
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if frame["type"] == "ready":
                ready = frame
            else:
                preamble.append(frame)
                print("<-", frame)

        print("<-", ready)
        transcribing = ready.get("transcribing")
        if not transcribing:
            print("   note: transcription is OFF — audio ingestion must still work")

        events = []

        async def drain():
            try:
                while True:
                    events.append(json.loads(await ws.recv()))
            except Exception:
                pass

        reader = asyncio.create_task(drain())

        sent = 0
        for i in range(CHUNKS):
            chunk = tone_chunk(i)
            await ws.send(chunk)
            sent += len(chunk)
            await asyncio.sleep(CHUNK_MS / 1000)  # real-time pacing

        # Stats piggyback on inbound frames, so the counters for the last chunks
        # only surface on the next send. Pause past the stats interval, then
        # send one more frame to flush a stats report covering everything prior.
        await asyncio.sleep(1.1)
        await ws.send(tone_chunk(CHUNKS))
        sent += SAMPLES * 2
        await asyncio.sleep(0.4)
        reader.cancel()

        stats = [e for e in events if e["type"] == "stats"]
        transcripts = [e for e in events if e["type"] == "transcript"]

        print(f"-> sent {sent} bytes in {CHUNKS + 1} chunks")
        print(f"<- {len(stats)} stats frames, {len(transcripts)} transcript frames")
        if stats:
            print("<- last stats:", stats[-1])

        assert stats, "no stats frames received"

        # Counters must advance monotonically.
        for a, b in zip(stats, stats[1:]):
            assert b["bytes_received"] >= a["bytes_received"], "counters went backwards"

        last = stats[-1]

        # Every frame arrived whole — no splitting, no coalescing, no truncation.
        assert last["bytes_received"] == last["chunks_received"] * SAMPLES * 2, (
            f"frame boundaries corrupted: {last['bytes_received']} bytes across "
            f"{last['chunks_received']} chunks"
        )

        # The flush frame should have carried the counters up to the full set.
        assert last["chunks_received"] == CHUNKS + 1, (
            f"expected {CHUNKS + 1} chunks by flush, server saw "
            f"{last['chunks_received']}"
        )
        assert last["bytes_received"] == sent, (
            f"byte mismatch: server saw {last['bytes_received']}, client sent {sent}"
        )

        # Graceful degradation (DESIGN.md §9, failure mode 5): a dead STT
        # provider must not stop the pipeline ingesting audio.
        if not transcribing:
            assert last["chunks_received"] == CHUNKS + 1, (
                "audio ingestion stalled when transcription was unavailable — "
                "STT failure should degrade, not halt the pipeline"
            )
            print("   degradation OK: all audio ingested with STT unavailable")

    print("\nPASS — handshake, binary frames, and stats round-trip all work")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
