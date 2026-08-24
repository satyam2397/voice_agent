"""
End-to-end transcription test using synthesised speech.

Streams two different synthetic voices through the real pipeline
(WebSocket -> Deepgram -> diarization -> role resolution) and prints what comes
back. Verifies transcription and speaker separation without needing two humans.

Generate the input first (macOS):

    say -v Samantha -o /tmp/spk_a.aiff "..."
    say -v Alex     -o /tmp/spk_b.aiff "..."
    afconvert -f WAVE -d LEI16@16000 -c 1 /tmp/spk_a.aiff /tmp/spk_a.wav
    afconvert -f WAVE -d LEI16@16000 -c 1 /tmp/spk_b.aiff /tmp/spk_b.wav

Caveat: synthesised voices are clean, close-mic'd and never overlap. Real
far-field audio across a table is materially harder — this proves the wiring,
not the quality.
"""

import asyncio
import json
import sys
import wave

import websockets

URL = "ws://localhost:8000/ws/audio/speech-smoke"
CHUNK_MS = 200
SAMPLE_RATE = 16000
CHUNK_BYTES = SAMPLE_RATE * 2 * CHUNK_MS // 1000  # 16-bit mono


def read_pcm(path: str) -> bytes:
    with wave.open(path) as w:
        assert w.getframerate() == SAMPLE_RATE, f"{path}: expected 16 kHz"
        assert w.getnchannels() == 1, f"{path}: expected mono"
        assert w.getsampwidth() == 2, f"{path}: expected 16-bit"
        return w.readframes(w.getnframes())


async def main(paths: list[str]) -> int:
    audio = b"".join(read_pcm(p) for p in paths)
    print(f"streaming {len(audio)} bytes ({len(audio) / (SAMPLE_RATE * 2):.1f}s)\n")

    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({
            "type": "start",
            "sample_rate": SAMPLE_RATE,
            "encoding": "pcm_s16le",
            "channels": 1,
        }))

        finals: list[dict] = []
        prompted = asyncio.Event()

        async def reader():
            async for raw in ws:
                event = json.loads(raw)
                kind = event.get("type")

                if kind == "ready":
                    print(f"[ready] transcribing={event.get('transcribing')}\n")
                elif kind == "error":
                    print(f"[error] {event['message']}\n")
                elif kind == "transcript":
                    tag = event.get("speaker_tag")
                    who = event.get("speaker")
                    label = f"spk{tag}" if tag is not None else "spk?"
                    if event["is_final"]:
                        finals.append(event)
                        conf = event.get("confidence")
                        conf_s = f" ({conf:.2f})" if isinstance(conf, float) else ""
                        print(f"  FINAL [{label}/{who}]{conf_s}: {event['text']}")
                    else:
                        print(f"  ...   [{label}]: {event['text']}", end="\r")
                elif kind == "role_prompt":
                    print(f"\n[role_prompt] {json.dumps(event['speakers'], indent=2)}")
                    prompted.set()
                elif kind == "roles_assigned":
                    print(f"[roles_assigned] {event['roles']}\n")

        task = asyncio.create_task(reader())

        for i in range(0, len(audio), CHUNK_BYTES):
            await ws.send(audio[i : i + CHUNK_BYTES])
            await asyncio.sleep(CHUNK_MS / 1000)  # real-time pacing

        # Answer the role prompt if one arrived, to exercise that path too.
        if prompted.is_set():
            await ws.send(json.dumps({"type": "assign_role", "rep_tag": 0}))

        await asyncio.sleep(3.0)  # let trailing finals land
        task.cancel()

    print("\n" + "=" * 60)
    speakers = {e.get("speaker_tag") for e in finals}
    print(f"final segments : {len(finals)}")
    print(f"distinct voices: {sorted(s for s in speakers if s is not None)}")

    if not finals:
        print("\nFAIL — no transcripts returned")
        return 1
    if len(speakers - {None}) < 2:
        print("\nPARTIAL — transcription works, but diarization did not separate "
              "two speakers (short samples often cluster as one)")
        return 0

    print("\nPASS — transcription and speaker separation both working")
    return 0


if __name__ == "__main__":
    files = sys.argv[1:] or ["/tmp/spk_a.wav", "/tmp/spk_b.wav"]
    sys.exit(asyncio.run(main(files)))
