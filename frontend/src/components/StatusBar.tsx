import type { ConnectionState } from "../types";

interface Props {
  state: ConnectionState;
  bytesSent: number;
  chunksDropped: number;
  sampleRate: number | null;
  agentEnabled: boolean;
  lastTrigger: string | null;
  isRecording: boolean;
}

const LABEL: Record<ConnectionState, string> = {
  idle: "Not connected",
  connecting: "Connecting…",
  connected: "Connected",
  reconnecting: "Reconnecting…",
  error: "Connection error",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function StatusBar({
  state,
  bytesSent,
  chunksDropped,
  sampleRate,
  agentEnabled,
  lastTrigger,
  isRecording,
}: Props) {
  return (
    <div className="status-bar">
      <span className={`status-dot status-${state}`} aria-hidden="true" />
      <span className="status-label">{LABEL[state]}</span>

      <span className="status-sep" aria-hidden="true">
        ·
      </span>
      <span className="status-metric">{formatBytes(bytesSent)} sent</span>

      {sampleRate !== null && (
        <>
          <span className="status-sep" aria-hidden="true">
            ·
          </span>
          <span className="status-metric">
            {(sampleRate / 1000).toFixed(1)} kHz → 16 kHz
          </span>
        </>
      )}

      {isRecording && (
        <>
          <span className="status-sep" aria-hidden="true">
            ·
          </span>
          <span className={`status-metric ${agentEnabled ? "" : "warn"}`}>
            agent {agentEnabled ? "on" : "off"}
          </span>
        </>
      )}

      {lastTrigger && (
        <>
          <span className="status-sep" aria-hidden="true">
            ·
          </span>
          <span className="status-metric">{lastTrigger}</span>
        </>
      )}

      {chunksDropped > 0 && (
        <>
          <span className="status-sep" aria-hidden="true">
            ·
          </span>
          <span className="status-metric warn">
            {chunksDropped} chunk{chunksDropped === 1 ? "" : "s"} dropped
          </span>
        </>
      )}
    </div>
  );
}
