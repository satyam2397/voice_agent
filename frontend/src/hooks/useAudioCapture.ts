import { useCallback, useEffect, useRef, useState } from "react";

interface Options {
  /** Called with each ~200 ms PCM16 @ 16 kHz chunk. */
  onChunk: (pcm: ArrayBuffer) => void;
}

interface AudioCapture {
  isCapturing: boolean;
  level: number;
  error: string | null;
  sampleRate: number | null;
  start: () => Promise<void>;
  stop: () => void;
}

/**
 * Captures mic audio and emits 16 kHz PCM16 chunks.
 *
 * One device, one mixed stream — both people at the table are in this audio.
 * Speaker separation happens server-side via diarization, not here.
 */
export function useAudioCapture({ onChunk }: Options): AudioCapture {
  const [isCapturing, setIsCapturing] = useState(false);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [sampleRate, setSampleRate] = useState<number | null>(null);

  const contextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const nodeRef = useRef<AudioWorkletNode | null>(null);

  // Keep the latest callback without re-running start().
  const onChunkRef = useRef(onChunk);
  useEffect(() => {
    onChunkRef.current = onChunk;
  }, [onChunk]);

  const stop = useCallback(() => {
    nodeRef.current?.port.postMessage("stop");
    nodeRef.current?.disconnect();
    nodeRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    contextRef.current?.close();
    contextRef.current = null;

    setIsCapturing(false);
    setLevel(0);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          // No speaker playback in the room, so there is no echo to cancel —
          // and echo cancellation can gate far-field audio unhelpfully.
          echoCancellation: false,
          // Both help a device sitting on a table: the distributor is further
          // away and quieter than the rep holding the conversation.
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const context = new AudioContext();
      contextRef.current = context;
      setSampleRate(context.sampleRate);

      await context.audioWorklet.addModule("/audio-processor.js");

      const source = context.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(context, "audio-processor");
      nodeRef.current = node;

      node.port.onmessage = (event) => {
        const data = event.data;
        if (data.type === "audio") {
          onChunkRef.current(data.pcm as ArrayBuffer);
        } else if (data.type === "level") {
          setLevel(data.peak as number);
        }
      };

      // A worklet only runs while it is in a path to the destination. Route it
      // through a silent gain node so we do not play the mic back into the room.
      const silence = context.createGain();
      silence.gain.value = 0;
      source.connect(node);
      node.connect(silence);
      silence.connect(context.destination);

      setIsCapturing(true);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not access microphone";
      setError(message);
      stop();
    }
  }, [stop]);

  useEffect(() => stop, [stop]);

  return { isCapturing, level, error, sampleRate, start, stop };
}
