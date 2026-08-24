"""
Label schema constants, shared by the data builder, the trainer and serving.

Authoritative prose lives in LABEL_SCHEMA.md. This module is the machine-
readable version — if the two disagree, the markdown is the spec and this is
the bug.
"""

from __future__ import annotations

# --- categories -------------------------------------------------------------

TRIGGER_CATEGORIES = [
    "fund_factual",
    "fund_comparison",
    "objection_performance",
    "objection_cost",
    "objection_risk",
    "suitability_match",
    "historical_reference",
    "process_operational",
]

NO_TRIGGER_CATEGORIES = [
    "small_talk",
    "backchannel",
    "logistics",
    "soft_close",
    "unintelligible",
    "rep_turn",
]

CATEGORIES = TRIGGER_CATEGORIES + NO_TRIGGER_CATEGORIES
CATEGORY_TO_ID = {name: i for i, name in enumerate(CATEGORIES)}
ID_TO_CATEGORY = {i: name for name, i in CATEGORY_TO_ID.items()}

NUM_CATEGORIES = len(CATEGORIES)
assert NUM_CATEGORIES == 14, f"expected 14 categories, got {NUM_CATEGORIES}"


def is_trigger(category: str) -> bool:
    """The trigger label is derived from the category — they can never disagree."""
    if category not in CATEGORY_TO_ID:
        raise ValueError(f"unknown category: {category}")
    return category in TRIGGER_CATEGORIES


# --- model input ------------------------------------------------------------

SPEAKER_REP = "rep"
SPEAKER_DIST = "distributor"

MAX_CONTEXT_TURNS = 3   # previous turns shown to the model
MAX_SEQ_LENGTH = 160    # tokens; conversational turns are short


def render_input(context: list[tuple[str, str]], target: str) -> str:
    """
    Build the exact string the model sees, at train time and at serve time.

    Both paths must call this. A mismatch between how examples were rendered
    during training and how they are rendered in production is the classic
    silent accuracy killer — the model sees a format it was never trained on
    and degrades without erroring.
    """
    parts = []
    for speaker, text in context[-MAX_CONTEXT_TURNS:]:
        tag = "REP" if speaker == SPEAKER_REP else "DIST"
        parts.append(f"[{tag}] {text}")
    parts.append(f"[DIST] {target}")
    return " ".join(parts)


# --- split names ------------------------------------------------------------

SPLIT_TRAIN = "train"
SPLIT_VAL = "val"
SPLIT_TEST_NATURAL = "test_natural"
SPLIT_TEST_BALANCED = "test_balanced"

SPLITS = [SPLIT_TRAIN, SPLIT_VAL, SPLIT_TEST_NATURAL, SPLIT_TEST_BALANCED]

# Realistic share of distributor turns that warrant a card. Used to shape
# test_natural so precision/recall describe the deployed distribution.
NATURAL_TRIGGER_RATE = 0.15
