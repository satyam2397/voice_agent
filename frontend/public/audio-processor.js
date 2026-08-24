/**
 * AudioWorklet processor: mic -> 16 kHz mono PCM16 chunks.
 *
 * Runs on the audio thread. Receives 128-sample Float32 frames at the
 * AudioContext's native rate (usually 48 kHz), resamples to 16 kHz, converts to
 * signed 16-bit PCM, and posts ~200 ms buffers to the main thread.
 *
 * Why resample here rather than requesting a 16 kHz AudioContext: Chrome honors
 * that request, Safari does not reliably. Doing it ourselves works everywhere.
 *
 * Why PCM16 rather than Float32: half the bytes on the wire, and it is what STT
 * engines expect anyway.
 */

const TARGET_RATE = 16000;
const CHUNK_MS = 200;
const LEVEL_INTERVAL_MS = 50;

class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // `sampleRate` is a global in AudioWorkletGlobalScope.
    this.ratio = sampleRate / TARGET_RATE;
    this.samplesPerChunk = Math.round((TARGET_RATE * CHUNK_MS) / 1000);
    this.framesPerLevel = Math.max(
      1,
      Math.round((sampleRate * LEVEL_INTERVAL_MS) / 1000 / 128)
    );

    this.pending = new Float32Array(0); // input samples not yet consumed
    this.offset = 0; // fractional read position carried between calls
    this.out = new Int16Array(this.samplesPerChunk);
    this.outLen = 0;

    this.peak = 0;
    this.frameCount = 0;
    this.running = true;

    this.port.onmessage = (event) => {
      if (event.data === "stop") this.running = false;
    };
  }

  process(inputs) {
    if (!this.running) return false;

    const channel = inputs[0]?.[0];
    if (!channel) return true;

    // Append this frame to whatever we could not consume last time.
    const buf = new Float32Array(this.pending.length + channel.length);
    buf.set(this.pending, 0);
    buf.set(channel, this.pending.length);

    let pos = this.offset;

    // Box-filter decimation: average the input window for each output sample.
    // Cheap anti-aliasing — naive sample-picking would fold high frequencies
    // down into the speech band as audible artefacts.
    while (pos + this.ratio <= buf.length) {
      const start = Math.floor(pos);
      const end = Math.floor(pos + this.ratio);

      let sum = 0;
      let n = 0;
      for (let i = start; i < end && i < buf.length; i++) {
        sum += buf[i];
        n++;
      }

      let s = n > 0 ? sum / n : 0;
      if (s > 1) s = 1;
      else if (s < -1) s = -1;

      const magnitude = s < 0 ? -s : s;
      if (magnitude > this.peak) this.peak = magnitude;

      this.out[this.outLen++] = s < 0 ? s * 0x8000 : s * 0x7fff;

      if (this.outLen === this.samplesPerChunk) {
        const chunk = this.out.slice();
        this.port.postMessage({ type: "audio", pcm: chunk.buffer }, [
          chunk.buffer,
        ]);
        this.outLen = 0;
      }

      pos += this.ratio;
    }

    // Keep the unconsumed tail plus the fractional offset, so resampling does
    // not drift on rates that are not an integer multiple of 16 kHz (44.1 kHz).
    const consumed = Math.floor(pos);
    this.pending = buf.slice(consumed);
    this.offset = pos - consumed;

    if (++this.frameCount >= this.framesPerLevel) {
      this.port.postMessage({ type: "level", peak: this.peak });
      this.frameCount = 0;
      this.peak = 0;
    }

    return true;
  }
}

registerProcessor("audio-processor", AudioProcessor);
