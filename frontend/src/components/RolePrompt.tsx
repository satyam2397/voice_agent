import type { SpeakerOption } from "../types";

interface Props {
  speakers: SpeakerOption[];
  onAssign: (repTag: number) => void;
}

/**
 * Deepgram tells us there are two voices; it cannot tell us which one is the
 * rep. One tap resolves it, because getting it wrong inverts every downstream
 * trigger decision for the rest of the conversation.
 */
export function RolePrompt({ speakers, onAssign }: Props) {
  return (
    <div className="role-prompt" role="dialog" aria-label="Identify yourself">
      <p className="role-prompt-title">Which voice is you?</p>
      <p className="role-prompt-hint">
        Two speakers detected. Tap the one that is you — everyone else is the
        distributor.
      </p>

      <div className="role-options">
        {speakers.map((speaker) => (
          <button
            key={speaker.tag}
            className="role-option"
            onClick={() => onAssign(speaker.tag)}
          >
            <span className="role-option-label">Speaker {speaker.tag + 1}</span>
            <span className="role-option-sample">“{speaker.sample}”</span>
          </button>
        ))}
      </div>
    </div>
  );
}
