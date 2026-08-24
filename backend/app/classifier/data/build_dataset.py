"""
Assemble the classifier dataset from the seed corpus and templates.

    ./.venv/bin/python -m app.classifier.data.build_dataset

Writes JSONL per split into app/classifier/data/ and prints a report.

The build FAILS rather than warns on:
  - template leakage between train/val and test_natural
  - a category with too few examples to learn
  - test_natural base rate drifting far from realistic

A dataset that quietly violates one of those produces a number that looks fine
and means nothing, which is worse than no number.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classifier.data import templates as T  # noqa: E402
from app.classifier.data.asr_noise import degrade, normalise  # noqa: E402
from app.classifier.data.seed_core import (  # noqa: E402
    CORE_BY_CATEGORY,
    HARD_NEGATIVE_PAIRS,
)
from app.classifier.data.test_natural import TEST_NATURAL  # noqa: E402
from app.classifier.schema import (  # noqa: E402
    CATEGORIES,
    MAX_CONTEXT_TURNS,
    NATURAL_TRIGGER_RATE,
    SPEAKER_DIST,
    SPEAKER_REP,
    is_trigger,
)

OUT_DIR = Path(__file__).resolve().parent
SEED = 13

# Share of train/val rows that get ASR corruption.
ASR_FRACTION = 0.45

# Expansion target per category before splitting.
EXPAND_PER_CATEGORY = 190

MIN_PER_CATEGORY = 40


def make_context(rng: random.Random, category: str) -> list[tuple[str, str]]:
    """A plausible one-to-three turn lead-in."""
    n = rng.choice([1, 2, 2, 3])
    turns: list[tuple[str, str]] = []
    for i in range(n):
        if i % 2 == 0:
            turns.append((SPEAKER_REP, rng.choice(T.REP_CONTEXT)))
        else:
            turns.append((SPEAKER_DIST, rng.choice(T.DIST_CONTEXT)))
    # historical_reference reads oddly without a rep turn immediately prior
    if category == "historical_reference" and turns and turns[-1][0] != SPEAKER_REP:
        turns.append((SPEAKER_REP, rng.choice(T.REP_CONTEXT)))
    return turns[-MAX_CONTEXT_TURNS:]


def fill(template: str, rng: random.Random) -> str:
    out = template
    for slot, values in T.SLOTS.items():
        token = "{" + slot + "}"
        while token in out:
            out = out.replace(token, rng.choice(values), 1)
    return " ".join(out.split())


def expand(rng: random.Random) -> list[dict]:
    rows: list[dict] = []

    # 1. seed core, verbatim
    for category, examples in CORE_BY_CATEGORY.items():
        for text in examples:
            rows.append({"text": normalise(text), "category": category,
                         "source": "core"})

    # 2. hard-negative pairs, both sides, linked
    for pos_text, pos_cat, neg_text, neg_cat in HARD_NEGATIVE_PAIRS:
        pair_id = f"hn_{len(rows)}"
        rows.append({"text": normalise(pos_text), "category": pos_cat,
                     "source": "hard_negative", "pair": pair_id})
        rows.append({"text": normalise(neg_text), "category": neg_cat,
                     "source": "hard_negative", "pair": pair_id})

    # 3. template expansion up to the per-category target
    for category, frames in T.TEMPLATES.items():
        have = sum(1 for r in rows if r["category"] == category)
        seen: set[str] = set()
        attempts = 0
        while have < EXPAND_PER_CATEGORY and attempts < EXPAND_PER_CATEGORY * 12:
            attempts += 1
            text = normalise(fill(rng.choice(frames), rng))
            if not text or text in seen:
                continue
            seen.add(text)
            rows.append({"text": text, "category": category, "source": "template"})
            have += 1

    return rows


def attach_context_and_noise(rows: list[dict], rng: random.Random) -> list[dict]:
    out = []
    for row in rows:
        context = make_context(rng, row["category"])
        text = row["text"]
        degraded = rng.random() < ASR_FRACTION
        if degraded:
            text = degrade(text, rng)
            context = [(s, degrade(t, rng, intensity=0.6)) for s, t in context]
        if not text.strip():
            continue
        out.append({
            **row,
            "text": text,
            "context": [{"speaker": s, "text": t} for s, t in context],
            "asr_degraded": degraded,
            "trigger": is_trigger(row["category"]),
        })
    return out


def ngrams(text: str, n: int = 4) -> set[str]:
    words = text.split()
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def check_leakage(train_rows: list[dict], test_rows: list[dict]) -> list[str]:
    """
    Fail if a test row shares a 4-gram with any training row.

    This is the property that makes the test number mean generalisation rather
    than template memorisation.
    """
    train_grams: set[str] = set()
    for r in train_rows:
        train_grams |= ngrams(r["text"])

    offenders = []
    for r in test_rows:
        overlap = ngrams(r["text"]) & train_grams
        if overlap:
            offenders.append(f"{r['text']!r} shares {sorted(overlap)[:2]}")
    return offenders


def build_test_natural(rng: random.Random) -> list[dict]:
    rows = []
    for text, category in TEST_NATURAL:
        context = make_context(rng, category)
        rows.append({
            "text": normalise(text),
            "category": category,
            "trigger": is_trigger(category),
            "context": [{"speaker": s, "text": t} for s, t in context],
            "source": "handwritten",
            "asr_degraded": False,
            "audited": False,
        })
    return rows


def build_test_balanced(pool: list[dict], rng: random.Random, per_class: int = 18):
    """
    Diagnostic split — per-category confusion only, never the headline number.

    Takes at most a quarter of any category. A flat per_class quota starves
    small categories: with 14 seed rows and a quota of 18, `unintelligible`
    lost every example to this split and had none left to train on.
    """
    by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for row in pool:
        by_cat[row["category"]].append(row)

    out = []
    for _, rows in by_cat.items():
        rng.shuffle(rows)
        take = min(per_class, max(1, len(rows) // 4))
        out.extend(rows[:take])
    return out


def write(rows: list[dict], name: str) -> Path:
    path = OUT_DIR / f"{name}.jsonl"
    with path.open("w") as f:
        for i, row in enumerate(rows):
            f.write(json.dumps({"id": f"{name}_{i:05d}", "split": name, **row}) + "\n")
    return path


def report(name: str, rows: list[dict]) -> None:
    total = len(rows)
    triggers = sum(1 for r in rows if r["trigger"])
    degraded = sum(1 for r in rows if r.get("asr_degraded"))
    print(f"\n{name}: {total} rows | trigger {triggers} ({triggers / total:.0%}) "
          f"| asr-degraded {degraded / total:.0%}")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    for category in CATEGORIES:
        bar = "#" * max(1, counts.get(category, 0) // 4)
        print(f"    {category:<24} {counts.get(category, 0):>4}  {bar}")


def main() -> int:
    rng = random.Random(SEED)

    pool = attach_context_and_noise(expand(rng), rng)
    rng.shuffle(pool)

    test_balanced = build_test_balanced(pool, rng)
    balanced_ids = {id(r) for r in test_balanced}
    remaining = [r for r in pool if id(r) not in balanced_ids]

    split_at = int(len(remaining) * 0.85)
    train, val = remaining[:split_at], remaining[split_at:]
    test_natural = build_test_natural(rng)

    problems: list[str] = []

    # 1. template leakage — the one that invalidates the headline metric
    leaks = check_leakage(train + val, test_natural)
    if leaks:
        problems.append(
            f"{len(leaks)} test rows share 4-grams with training data:\n    "
            + "\n    ".join(leaks[:8])
        )

    # 2. every category must be learnable
    for category in CATEGORIES:
        n = sum(1 for r in train if r["category"] == category)
        if n < MIN_PER_CATEGORY:
            problems.append(f"category '{category}' has only {n} training rows")

    # 3. test_natural must reflect the deployed base rate
    rate = sum(1 for r in test_natural if r["trigger"]) / len(test_natural)
    if abs(rate - NATURAL_TRIGGER_RATE) > 0.06:
        problems.append(
            f"test_natural trigger rate {rate:.0%} is far from the expected "
            f"{NATURAL_TRIGGER_RATE:.0%}"
        )

    for name, rows in (
        ("train", train), ("val", val),
        ("test_natural", test_natural), ("test_balanced", test_balanced),
    ):
        write(rows, name)
        report(name, rows)

    print("\n" + "=" * 64)
    if problems:
        print("BUILD FAILED\n")
        for p in problems:
            print("  ✗", p)
        return 1

    print("OK  no template leakage between train/val and test_natural")
    print("OK  every category has enough training rows")
    print(f"OK  test_natural trigger rate {rate:.0%}")
    print(f"\nwrote 4 splits to {OUT_DIR}")
    print("\nNEXT: audit test_natural.jsonl by hand — it is the only split whose")
    print("      number you should quote.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
