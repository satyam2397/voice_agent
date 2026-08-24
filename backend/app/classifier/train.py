"""
Fine-tune the two-head classifier, then choose a threshold.

    ./.venv/bin/python -m app.classifier.train

Runs on CUDA (Colab), MPS (Apple Silicon) or CPU. At ~2k rows this is a small
job — roughly 2 minutes on a T4, 10-15 on a laptop CPU.

The threshold is NOT 0.5. It is chosen on the validation split as: maximise
recall subject to precision >= TARGET_PRECISION. That encodes the actual cost
asymmetry — interrupting a live sales meeting wrongly is worse than staying
quiet — as a number you can defend rather than a round default.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from transformers import get_linear_schedule_with_warmup

from app.classifier.dataset import (
    TurnDataset,
    class_weights,
    load_split,
    trigger_pos_weight,
)
from app.classifier.model import BASE_MODEL, TriggerCategoryModel, get_tokenizer, pick_device
from app.classifier.schema import NUM_CATEGORIES

OUT_DIR = Path(__file__).resolve().parent / "checkpoints"

# Precision floor for the trigger head. Below this the tool interrupts too
# often and the rep stops trusting it, which is unrecoverable.
TARGET_PRECISION = 0.85

# The trigger decision is what gates spend and interruption; category only
# routes tools afterwards. Weight the losses accordingly.
TRIGGER_LOSS_WEIGHT = 1.0
CATEGORY_LOSS_WEIGHT = 0.6


def evaluate(model, loader, device) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    model.eval()
    probs, trig_true, cat_pred, cat_true = [], [], [], []
    with torch.no_grad():
        for batch in loader:
            ids = batch["input_ids"].to(device)
            mask = batch["attention_mask"].to(device)
            t_logit, c_logit = model(ids, mask)
            probs.append(torch.sigmoid(t_logit).cpu())
            trig_true.append(batch["trigger"])
            cat_pred.append(c_logit.argmax(-1).cpu())
            cat_true.append(batch["category"])
    return (
        torch.cat(probs),
        torch.cat(trig_true),
        torch.cat(cat_pred),
        torch.cat(cat_true),
    )


def prf(probs: torch.Tensor, truth: torch.Tensor, threshold: float) -> dict:
    pred = (probs >= threshold).float()
    tp = float(((pred == 1) & (truth == 1)).sum())
    fp = float(((pred == 1) & (truth == 0)).sum())
    fn = float(((pred == 0) & (truth == 1)).sum())
    tn = float(((pred == 0) & (truth == 0)).sum())

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def choose_threshold(probs, truth, target_precision: float = TARGET_PRECISION) -> dict:
    """Highest recall among thresholds meeting the precision floor."""
    curve = [prf(probs, truth, t / 100) for t in range(5, 100, 1)]
    viable = [c for c in curve if c["precision"] >= target_precision and c["recall"] > 0]
    chosen = max(viable, key=lambda c: c["recall"]) if viable else max(curve, key=lambda c: c["f1"])
    return {"chosen": chosen, "curve": curve, "met_target": bool(viable)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--output", type=Path, default=OUT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="smoke test on N rows")
    args = parser.parse_args()

    device = pick_device()
    print(f"device: {device}")

    tokenizer = get_tokenizer()
    train_rows = load_split("train")
    val_rows = load_split("val")
    if args.limit:
        train_rows, val_rows = train_rows[: args.limit], val_rows[: args.limit // 4 or 8]

    print(f"train {len(train_rows)} | val {len(val_rows)}")

    train_ds = TurnDataset(train_rows, tokenizer)
    val_ds = TurnDataset(val_rows, tokenizer)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=64)

    model = TriggerCategoryModel().to(device)

    trigger_loss = nn.BCEWithLogitsLoss(pos_weight=trigger_pos_weight(train_rows).to(device))
    category_loss = nn.CrossEntropyLoss(
        weight=class_weights(train_rows, NUM_CATEGORIES).to(device)
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer, int(total_steps * 0.1), total_steps
    )

    started = time.monotonic()
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for batch in train_loader:
            optimizer.zero_grad()
            ids = batch["input_ids"].to(device)
            mask = batch["attention_mask"].to(device)
            t_logit, c_logit = model(ids, mask)

            loss = (
                TRIGGER_LOSS_WEIGHT * trigger_loss(t_logit, batch["trigger"].to(device))
                + CATEGORY_LOSS_WEIGHT * category_loss(c_logit, batch["category"].to(device))
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            running += loss.detach().item()

        probs, truth, cat_pred, cat_true = evaluate(model, val_loader, device)
        at_half = prf(probs, truth, 0.5)
        cat_acc = float((cat_pred == cat_true).float().mean())
        print(
            f"epoch {epoch}/{args.epochs}  loss {running / len(train_loader):.4f}  "
            f"val P {at_half['precision']:.3f} R {at_half['recall']:.3f} "
            f"F1 {at_half['f1']:.3f}  cat-acc {cat_acc:.3f}"
        )

    elapsed = time.monotonic() - started
    print(f"\ntrained in {elapsed:.0f}s")

    # --- threshold selection on val --------------------------------------
    probs, truth, _, _ = evaluate(model, val_loader, device)
    result = choose_threshold(probs, truth)
    chosen = result["chosen"]

    print("\nthreshold sweep (val):")
    for c in result["curve"]:
        if abs(c["threshold"] * 100 % 10) < 1e-6:
            print(f"  t={c['threshold']:.2f}  P {c['precision']:.3f}  R {c['recall']:.3f}  F1 {c['f1']:.3f}")

    if not result["met_target"]:
        print(f"\n  WARNING: no threshold reached precision {TARGET_PRECISION}; "
              f"fell back to best F1")
    print(
        f"\nchosen threshold {chosen['threshold']:.2f} — "
        f"P {chosen['precision']:.3f} R {chosen['recall']:.3f} F1 {chosen['f1']:.3f}"
    )

    # --- save -------------------------------------------------------------
    args.output.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), args.output / "model.pt")
    tokenizer.save_pretrained(args.output)
    (args.output / "meta.json").write_text(
        json.dumps(
            {
                "base_model": BASE_MODEL,
                "threshold": chosen["threshold"],
                "target_precision": TARGET_PRECISION,
                "val_metrics": chosen,
                "epochs": args.epochs,
                "train_rows": len(train_rows),
                "trained_seconds": round(elapsed),
            },
            indent=2,
        )
    )
    print(f"\nsaved to {args.output}")
    print("NEXT: python -m app.classifier.evaluate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
