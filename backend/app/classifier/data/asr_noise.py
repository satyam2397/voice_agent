"""
Make clean text look like ASR output.

The model is served lowercase, thinly punctuated, disfluent text with the
occasional wrong word. Training only on tidy prose builds train/serve skew
directly into the system: the encoder learns that well-formed input is normal
and degrades on exactly the distribution it will actually see.

Everything here is seeded and deterministic so a dataset rebuild is reproducible.
"""

from __future__ import annotations

import random

FILLERS = ["um", "uh", "er", "like", "you know", "i mean"]

# Plausible confusions for this domain — homophones and near-misses a speech
# model actually makes, not random character noise.
SUBSTITUTIONS = {
    "expense": ["expanse", "expence"],
    "ratio": ["racio"],
    "returns": ["retunes", "return"],
    "fund": ["found", "fun"],
    "risk": ["rist"],
    "aum": ["a u m", "am"],
    "sip": ["sipp", "sept"],
    "nav": ["nab"],
    "cap": ["cab"],
    "load": ["loan"],
    "yield": ["field"],
    "equity": ["equety"],
    "debt": ["det", "death"],
    "corpus": ["carpus"],
    "ter": ["tear"],
    "cagr": ["c a g r", "cager"],
    "drawdown": ["draw down"],
    "benchmark": ["bench mark"],
    "volatile": ["volatel"],
    "portfolio": ["portfolia"],
}

STOPWORDS_DROPPABLE = ["the", "a", "is", "to", "of", "that", "it", "and"]


def degrade(text: str, rng: random.Random, intensity: float = 1.0) -> str:
    """
    Apply ASR-like corruption. `intensity` scales how aggressive it is.

    Order matters: substitutions run on clean tokens, then fillers get
    inserted, then punctuation is stripped last.
    """
    words = text.split()
    if not words:
        return text

    # 1. word substitution
    if rng.random() < 0.30 * intensity:
        idxs = [i for i, w in enumerate(words) if w.strip(".,?").lower() in SUBSTITUTIONS]
        if idxs:
            i = rng.choice(idxs)
            key = words[i].strip(".,?").lower()
            words[i] = rng.choice(SUBSTITUTIONS[key])

    # 2. filler insertion
    if rng.random() < 0.35 * intensity:
        pos = rng.randint(0, len(words))
        words.insert(pos, rng.choice(FILLERS))

    # 3. false start — repeat a short word
    if rng.random() < 0.18 * intensity and len(words) > 2:
        i = rng.randrange(len(words))
        if len(words[i]) <= 5:
            words.insert(i, words[i])

    # 4. drop a stopword
    if rng.random() < 0.20 * intensity and len(words) > 4:
        idxs = [i for i, w in enumerate(words) if w.lower() in STOPWORDS_DROPPABLE]
        if idxs:
            del words[rng.choice(idxs)]

    out = " ".join(words)

    # 5. punctuation: ASR is inconsistent about it
    roll = rng.random()
    if roll < 0.55 * intensity:
        out = out.replace(",", "").replace(".", "").replace("?", "")
    elif roll < 0.70 * intensity:
        out = out.replace(",", "")

    return out.lower().strip()


def normalise(text: str) -> str:
    """Light cleanup applied to every example, degraded or not."""
    return " ".join(text.lower().split()).strip()
