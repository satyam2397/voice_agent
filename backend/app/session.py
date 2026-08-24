"""
Per-conversation state that lives for the length of one recording.

Its only real job today is resolving Deepgram's diarization labels
(`speaker 0` / `speaker 1`) onto actual roles (rep / distributor).

Why this is not inferred automatically: the same words flip the trigger
decision depending on who said them. "What kind of returns are you seeing?"
is a card-worthy product question from the distributor, and a rep qualifying
the distributor's own book when the rep says it. A heuristic that gets this
wrong fails silently and inverts every decision for the rest of the
conversation, so the rep confirms it once, by tapping. See DESIGN.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpeakerSample:
    tag: int
    text: str


@dataclass
class ConversationSession:
    conversation_id: str

    # Who the rep is meeting. Comes from the frontend on connect and is the
    # only tenant scope any tool call ever uses — never from the model.
    distributor_id: str = ""

    # Diarization tag -> role. Empty until the rep confirms.
    roles: dict[int, str] = field(default_factory=dict)

    # First thing we heard each speaker say, used to prompt the rep.
    samples: dict[int, SpeakerSample] = field(default_factory=dict)

    prompted: bool = False

    # Rolling window of final turns, most recent last.
    turns: list[tuple[str, str]] = field(default_factory=list)

    def add_turn(self, speaker: str, text: str, *, keep: int = 8) -> None:
        self.turns.append((speaker, text))
        del self.turns[:-keep]

    def window(self) -> str:
        return "\n".join(f"[{speaker}] {text}" for speaker, text in self.turns)

    def note_speaker(self, tag: int | None, text: str) -> None:
        """Record the first utterance from each distinct speaker."""
        if tag is None or tag in self.samples:
            return
        cleaned = text.strip()
        if len(cleaned) < 2:
            return
        self.samples[tag] = SpeakerSample(tag=tag, text=cleaned)

    def should_prompt_for_roles(self) -> bool:
        """True once we can actually tell two people apart and still don't know who is who."""
        return not self.roles and not self.prompted and len(self.samples) >= 2

    def assign(self, rep_tag: int) -> None:
        """The rep identified themselves; everyone else is the distributor."""
        self.roles = {rep_tag: "rep"}
        for tag in self.samples:
            if tag != rep_tag:
                self.roles[tag] = "distributor"

    def role_for(self, tag: int | None) -> str:
        if tag is None:
            return "unknown"
        if not self.roles:
            return "unknown"
        # A speaker appearing after assignment is not the rep — the rep is the
        # one holding the device and was present from the start.
        return self.roles.get(tag, "distributor")

    def speaker_options(self) -> list[dict]:
        return [
            {"tag": s.tag, "sample": s.text}
            for s in sorted(self.samples.values(), key=lambda s: s.tag)
        ]
