import { useEffect, useRef } from "react";
import type { SpeakerOption, Turn } from "../types";
import { RolePrompt } from "./RolePrompt";

interface Props {
  turns: Turn[];
  interim: Turn | null;
  isRecording: boolean;
  transcribing: boolean;
  rolePrompt: SpeakerOption[] | null;
  onAssignRole: (repTag: number) => void;
}

function speakerLabel(turn: Turn): string {
  if (turn.speaker === "rep") return "You";
  if (turn.speaker === "distributor") return "Distributor";
  return turn.speakerTag !== null ? `Speaker ${turn.speakerTag + 1}` : "Speaker";
}

export function TranscriptPanel({
  turns,
  interim,
  isRecording,
  transcribing,
  rolePrompt,
  onAssignRole,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, interim?.text, rolePrompt]);

  const empty = turns.length === 0 && !interim;

  return (
    <section className="panel transcript-panel">
      <header className="panel-header">
        <h2>Transcript</h2>
        {isRecording && transcribing && <span className="live-badge">Live</span>}
        {isRecording && !transcribing && (
          <span className="live-badge muted">No transcription</span>
        )}
      </header>

      <div className="panel-body">
        {empty && (
          <p className="empty-state">
            {isRecording
              ? "Listening — speech will appear here."
              : "Press Start listening to begin."}
          </p>
        )}

        {turns.map((turn) => (
          <div key={turn.id} className={`turn speaker-${turn.speaker}`}>
            <div className="turn-meta">
              <span className="turn-speaker">{speakerLabel(turn)}</span>
              {turn.confidence !== null && turn.confidence < 0.6 && (
                <span
                  className="low-confidence"
                  title="Low transcription confidence — far-field audio is hard"
                >
                  low confidence
                </span>
              )}
            </div>
            <p className="turn-text">{turn.text}</p>
          </div>
        ))}

        {interim && (
          <div className={`turn interim speaker-${interim.speaker}`}>
            <div className="turn-meta">
              <span className="turn-speaker">{speakerLabel(interim)}</span>
            </div>
            <p className="turn-text">{interim.text}</p>
          </div>
        )}

        {rolePrompt && (
          <RolePrompt speakers={rolePrompt} onAssign={onAssignRole} />
        )}

        <div ref={endRef} />
      </div>
    </section>
  );
}
