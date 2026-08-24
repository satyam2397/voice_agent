"""
Two heads on one shared DistilBERT encoder.

  trigger  — sigmoid, one logit, TUNABLE THRESHOLD
  category — softmax over 14 classes

The trigger head is deliberately not derived from the category argmax. Keeping
it separate is what preserves the threshold as an independent lever for the
fail-closed cost asymmetry: a false positive burns an LLM call *and* erodes the
rep's trust, a false negative only costs a missed assist. That asymmetry is
expressed as a threshold, and you cannot tune the argmax of a softmax.

`distilbert-base-uncased` specifically: it lowercases during tokenization,
which matches ASR output. A cased model would spend capacity on capitalisation
our transcripts do not carry.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from transformers import AutoConfig, AutoModel, AutoTokenizer

from app.classifier.schema import NUM_CATEGORIES

BASE_MODEL = "distilbert-base-uncased"


class TriggerCategoryModel(nn.Module):
    def __init__(
        self,
        base_model: str = BASE_MODEL,
        num_categories: int = NUM_CATEGORIES,
        dropout: float = 0.1,
        from_pretrained: bool = True,
    ) -> None:
        super().__init__()
        if from_pretrained:
            self.encoder = AutoModel.from_pretrained(base_model)
        else:
            # Used when reloading a fine-tuned checkpoint: build the
            # architecture without pulling pretrained weights we overwrite.
            self.encoder = AutoModel.from_config(AutoConfig.from_pretrained(base_model))

        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.trigger_head = nn.Linear(hidden, 1)
        self.category_head = nn.Linear(hidden, num_categories)

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        # DistilBERT has no pooler — take the [CLS] position directly.
        pooled = self.dropout(out.last_hidden_state[:, 0])
        return self.trigger_head(pooled).squeeze(-1), self.category_head(pooled)


def get_tokenizer(base_model: str = BASE_MODEL):
    return AutoTokenizer.from_pretrained(base_model)


def pick_device() -> torch.device:
    """CUDA on Colab, MPS on Apple Silicon, CPU otherwise."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")
