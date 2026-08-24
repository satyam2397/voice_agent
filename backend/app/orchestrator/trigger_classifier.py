"""
Decides, turn by turn, whether the agent should run.

PLACEHOLDER. This is keyword matching, not the real classifier. The designed
mechanism is a fine-tuned DistilBERT with a trigger head and a category head
(see DESIGN.md §6 and app/classifier/LABEL_SCHEMA.md); it needs a labelled
dataset that does not exist yet.

Keeping the interface stable means swapping in the trained model later is a
change to this file only.

Fail closed: anything uncertain resolves to "do not trigger". Calling the LLM
is the slow, expensive path and should never be the default under doubt.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# Suppress a second card for this long after one fires. A rep mid-conversation
# cannot read a stack of cards, so this is a product constraint as much as a
# cost one — and it stays in the orchestrator even once the model lands.
COOLDOWN_S = 20.0

_KEYWORDS = (
    "expense ratio", "expense", "fee", "fees", "commission",
    "return", "returns", "performance", "performed", "cagr",
    "compare", "versus", "vs", "against", "benchmark",
    "risk", "risky", "volatile", "volatility", "drawdown",
    "minimum", "lock in", "lock-in", "exit load", "sip",
    "aum", "track record", "fund manager",
)


@dataclass
class TriggerDecision:
    triggered: bool
    confidence: float
    reason: str


class TriggerClassifier:
    def __init__(self, cooldown_s: float = COOLDOWN_S) -> None:
        self._cooldown_s = cooldown_s
        self._last_fired_at: float | None = None

    def classify(self, *, speaker: str, text: str) -> TriggerDecision:
        cleaned = (text or "").strip()

        # The co-pilot helps the rep answer the distributor. The rep's own
        # speech is not a trigger candidate.
        if speaker != "distributor":
            return TriggerDecision(False, 1.0, "not_distributor")

        if len(cleaned.split()) < 3:
            return TriggerDecision(False, 0.9, "too_short")

        if self._in_cooldown():
            return TriggerDecision(False, 1.0, "cooldown")

        lowered = cleaned.lower()
        hit = next((k for k in _KEYWORDS if k in lowered), None)
        if hit:
            return TriggerDecision(True, 0.8, f"keyword:{hit}")

        if cleaned.endswith("?"):
            return TriggerDecision(True, 0.6, "question")

        return TriggerDecision(False, 0.5, "no_signal")

    def note_fired(self) -> None:
        self._last_fired_at = time.monotonic()

    def _in_cooldown(self) -> bool:
        if self._last_fired_at is None:
            return False
        return (time.monotonic() - self._last_fired_at) < self._cooldown_s
