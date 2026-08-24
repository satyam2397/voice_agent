"""
Loading and tokenising the built splits.

Every example is rendered through `schema.render_input`, the same function
serving uses. If training and serving disagree about how a conversation window
becomes a string, the model degrades silently in production — no error, just a
quietly worse classifier. One function, both paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch.utils.data import Dataset

from app.classifier.schema import CATEGORY_TO_ID, MAX_SEQ_LENGTH, render_input

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_split(name: str) -> list[dict]:
    path = DATA_DIR / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing — run: python -m app.classifier.data.build_dataset"
        )
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def render_row(row: dict) -> str:
    context = [(c["speaker"], c["text"]) for c in row.get("context", [])]
    return render_input(context, row["text"])


class TurnDataset(Dataset):
    def __init__(self, rows: list[dict], tokenizer, max_length: int = MAX_SEQ_LENGTH):
        self.rows = rows
        self.encodings = tokenizer(
            [render_row(r) for r in rows],
            truncation=True,
            padding="max_length",
            max_length=max_length,
            return_tensors="pt",
        )
        self.trigger = torch.tensor(
            [float(r["trigger"]) for r in rows], dtype=torch.float
        )
        self.category = torch.tensor(
            [CATEGORY_TO_ID[r["category"]] for r in rows], dtype=torch.long
        )

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> dict:
        return {
            "input_ids": self.encodings["input_ids"][i],
            "attention_mask": self.encodings["attention_mask"][i],
            "trigger": self.trigger[i],
            "category": self.category[i],
        }


def class_weights(rows: list[dict], num_classes: int) -> torch.Tensor:
    """
    Inverse-frequency weights so rare categories are not simply ignored.

    Without this the model can score well by never predicting the small
    classes, which is exactly the failure the per-category confusion matrix
    exists to expose.
    """
    counts = torch.zeros(num_classes)
    for row in rows:
        counts[CATEGORY_TO_ID[row["category"]]] += 1
    counts = counts.clamp(min=1.0)
    weights = counts.sum() / (num_classes * counts)
    return weights


def trigger_pos_weight(rows: list[dict]) -> torch.Tensor:
    """positive:negative ratio for BCE, so the minority class still matters."""
    pos = sum(1 for r in rows if r["trigger"])
    neg = len(rows) - pos
    return torch.tensor(max(neg, 1) / max(pos, 1), dtype=torch.float)
