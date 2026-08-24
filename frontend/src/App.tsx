import { useCallback, useMemo, useRef, useState } from "react";
import { useAudioCapture } from "./hooks/useAudioCapture";
import { useConversationSocket } from "./hooks/useConversationSocket";
import { RecordButton } from "./components/RecordButton";
import { LevelMeter } from "./components/LevelMeter";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { FlashCardPanel } from "./components/FlashCardPanel";
import { StatusBar } from "./components/StatusBar";
import { DistributorPicker } from "./components/DistributorPicker";
import type {
  FlashCard,
  ServerEvent,
  Speaker,
  SpeakerOption,
  Turn,
} from "./types";

function newConversationId(): string {
  return crypto.randomUUID();
}

export default function App() {
  const [conversationId] = useState(newConversationId);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [interim, setInterim] = useState<Turn | null>(null);
  const [cards, setCards] = useState<FlashCard[]>([]);
  const [transcribing, setTranscribing] = useState(false);
  const [agentEnabled, setAgentEnabled] = useState(false);
  const [rolePrompt, setRolePrompt] = useState<SpeakerOption[] | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [distributorId, setDistributorId] = useState<string | null>(null);
  const [lastTrigger, setLastTrigger] = useState<string | null>(null);

  const handleEvent = useCallback((event: ServerEvent) => {
    switch (event.type) {
      case "ready":
        setTranscribing(event.transcribing);
        setAgentEnabled(event.agent_enabled);
        break;

      case "transcript": {
        const turn: Turn = {
          id: event.id,
          speaker: event.speaker,
          speakerTag: event.speaker_tag,
          text: event.text,
          isFinal: event.is_final,
          confidence: event.confidence,
          ts: Date.now(),
        };
        if (event.is_final) {
          setInterim(null);
          setTurns((prev) => [...prev, turn]);
        } else {
          setInterim(turn);
        }
        break;
      }

      case "role_prompt":
        setRolePrompt(event.speakers);
        break;

      case "roles_assigned": {
        setRolePrompt(null);
        // Relabel everything already on screen — the rep just told us who was
        // who, and that applies retroactively to the whole conversation.
        const roles = event.roles;
        const resolve = (tag: number | null): Speaker => {
          if (tag === null) return "unknown";
          return roles[String(tag)] ?? "distributor";
        };
        setTurns((prev) =>
          prev.map((t) => ({ ...t, speaker: resolve(t.speakerTag) }))
        );
        setInterim((prev) =>
          prev ? { ...prev, speaker: resolve(prev.speakerTag) } : prev
        );
        break;
      }

      case "flash_card":
        setCards((prev) => [
          {
            id: event.id,
            content: event.content,
            triggerReason: event.trigger_reason,
            category: event.category,
            latencyMs: event.latency_ms,
            toolsUsed: event.tools_used ?? [],
            inputTokens: event.input_tokens ?? null,
            outputTokens: event.output_tokens ?? null,
            ts: Date.now(),
          },
          ...prev,
        ]);
        break;

      case "trigger":
        setLastTrigger(
          event.triggered
            ? `fired (${event.reason})`
            : `no trigger (${event.reason})`
        );
        break;

      case "card_skipped":
        setLastTrigger(`card skipped: ${event.reason}`);
        break;

      case "error":
        setBackendError(event.message);
        break;

      default:
        break;
    }
  }, []);

  const socket = useConversationSocket({
    conversationId,
    distributorId,
    onEvent: handleEvent,
  });

  // Hold the sender in a ref so useAudioCapture never needs to re-init.
  const sendAudioRef = useRef(socket.sendAudio);
  sendAudioRef.current = socket.sendAudio;

  const handleChunk = useCallback((pcm: ArrayBuffer) => {
    sendAudioRef.current(pcm);
  }, []);

  const audio = useAudioCapture({ onChunk: handleChunk });

  const start = useCallback(async () => {
    setBackendError(null);
    setTurns([]);
    setInterim(null);
    setRolePrompt(null);
    socket.connect();
    await audio.start();
  }, [socket, audio]);

  const stop = useCallback(() => {
    audio.stop();
    socket.disconnect();
    setInterim(null);
    setRolePrompt(null);
    setTranscribing(false);
  }, [audio, socket]);

  const assignRole = useCallback(
    (repTag: number) => {
      socket.sendControl({ type: "assign_role", rep_tag: repTag });
    },
    [socket]
  );

  const busy = useMemo(
    () => socket.state === "connecting" && !audio.isCapturing,
    [socket.state, audio.isCapturing]
  );

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <h1>Sales Co-Pilot</h1>
          <p className="tagline">
            One device on the table. It listens, and speaks up only when it can
            help.
          </p>
        </div>

        <div className="controls">
          <DistributorPicker
            selectedId={distributorId}
            disabled={audio.isCapturing}
            onSelect={setDistributorId}
          />
          <LevelMeter level={audio.level} active={audio.isCapturing} />
          <RecordButton
            isRecording={audio.isCapturing}
            disabled={busy || !distributorId}
            onStart={start}
            onStop={stop}
          />
        </div>
      </header>

      {audio.error && (
        <div className="banner error" role="alert">
          {audio.error}
        </div>
      )}

      {backendError && (
        <div className="banner warn" role="alert">
          {backendError}
        </div>
      )}

      <StatusBar
        state={socket.state}
        bytesSent={socket.bytesSent}
        chunksDropped={socket.chunksDropped}
        sampleRate={audio.sampleRate}
        agentEnabled={agentEnabled}
        lastTrigger={lastTrigger}
        isRecording={audio.isCapturing}
      />

      <main className="workspace">
        <TranscriptPanel
          turns={turns}
          interim={interim}
          isRecording={audio.isCapturing}
          transcribing={transcribing}
          rolePrompt={rolePrompt}
          onAssignRole={assignRole}
        />
        <FlashCardPanel cards={cards} />
      </main>
    </div>
  );
}
