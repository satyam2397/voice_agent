import { useCallback, useEffect, useRef, useState } from "react";
import type { ClientControl, ConnectionState, ServerEvent } from "../types";

/** Stop sending if the socket is this far behind — drop audio, never queue it. */
const MAX_BUFFERED_BYTES = 512 * 1024;

interface Options {
  conversationId: string;
  /** Who the rep is meeting — sent on connect, scopes every tool call. */
  distributorId: string | null;
  onEvent: (event: ServerEvent) => void;
}

interface ConversationSocket {
  state: ConnectionState;
  bytesSent: number;
  chunksDropped: number;
  connect: () => void;
  disconnect: () => void;
  sendAudio: (pcm: ArrayBuffer) => void;
  sendControl: (message: ClientControl) => void;
}

export function useConversationSocket({
  conversationId,
  distributorId,
  onEvent,
}: Options): ConversationSocket {
  const [state, setState] = useState<ConnectionState>("idle");
  const [bytesSent, setBytesSent] = useState(0);
  const [chunksDropped, setChunksDropped] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const wantOpenRef = useRef(false);
  const retryRef = useRef<number | null>(null);
  const attemptRef = useRef(0);

  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  // Read at handshake time, so reconnects pick up the current selection
  // without tearing down and rebuilding the socket callbacks.
  const distributorIdRef = useRef(distributorId);
  distributorIdRef.current = distributorId;

  const open = useCallback(() => {
    if (!wantOpenRef.current) return;
    if (socketRef.current?.readyState === WebSocket.OPEN) return;

    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${scheme}://${window.location.host}/ws/audio/${conversationId}`;

    setState(attemptRef.current === 0 ? "connecting" : "reconnecting");

    const socket = new WebSocket(url);
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;

    socket.onopen = () => {
      attemptRef.current = 0;
      setState("connected");
      // Handshake: describe the stream before any binary frames arrive.
      socket.send(
        JSON.stringify({
          type: "start",
          sample_rate: 16000,
          encoding: "pcm_s16le",
          channels: 1,
          distributor_id: distributorIdRef.current,
        })
      );
    };

    socket.onmessage = (event) => {
      if (typeof event.data !== "string") return;
      try {
        onEventRef.current(JSON.parse(event.data) as ServerEvent);
      } catch {
        // Ignore malformed frames rather than tearing down the stream.
      }
    };

    socket.onerror = () => setState("error");

    socket.onclose = () => {
      socketRef.current = null;
      if (!wantOpenRef.current) {
        setState("idle");
        return;
      }
      setState("reconnecting");
      const backoff = Math.min(1000 * 2 ** attemptRef.current, 10_000);
      attemptRef.current += 1;
      retryRef.current = window.setTimeout(open, backoff);
    };
  }, [conversationId]);

  const connect = useCallback(() => {
    wantOpenRef.current = true;
    attemptRef.current = 0;
    open();
  }, [open]);

  const disconnect = useCallback(() => {
    wantOpenRef.current = false;
    if (retryRef.current) {
      clearTimeout(retryRef.current);
      retryRef.current = null;
    }
    socketRef.current?.close();
    socketRef.current = null;
    setState("idle");
  }, []);

  const sendAudio = useCallback((pcm: ArrayBuffer) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;

    // Backpressure: dropping audio is recoverable, an unbounded queue is not.
    if (socket.bufferedAmount > MAX_BUFFERED_BYTES) {
      setChunksDropped((n) => n + 1);
      return;
    }

    socket.send(pcm);
    setBytesSent((n) => n + pcm.byteLength);
  }, []);

  const sendControl = useCallback((message: ClientControl) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify(message));
  }, []);

  useEffect(() => disconnect, [disconnect]);

  return {
    state,
    bytesSent,
    chunksDropped,
    connect,
    disconnect,
    sendAudio,
    sendControl,
  };
}
