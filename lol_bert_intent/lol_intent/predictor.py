from __future__ import annotations

from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .label_schema import LABEL_DESCRIPTIONS


class LolIntentPredictor:
    def __init__(self, model_dir: str | Path = "models/lol-bert-binary-intent", max_length: int = 96):
        self.model_dir = Path(model_dir)
        if not self.model_dir.exists():
            raise FileNotFoundError(
                f"Model directory not found: {self.model_dir}. "
                "Train first with: python -m lol_intent.train"
            )
        self.max_length = max_length
        self.device = torch.device("cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_dir)
        self.model.to(self.device)
        self.model.eval()

    def predict(self, text: str, top_k: int = 3) -> dict:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("text cannot be empty")

        encoded = self.tokenizer(
            clean_text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.no_grad():
            logits = self.model(**encoded).logits.squeeze(0)
            probs = torch.softmax(logits, dim=-1)

        k = max(1, min(top_k, probs.numel()))
        values, indices = torch.topk(probs, k=k)
        candidates = []
        for score, index in zip(values.cpu().tolist(), indices.cpu().tolist(), strict=True):
            label = self.model.config.id2label.get(index, str(index))
            candidates.append(
                {
                    "label": label,
                    "description": LABEL_DESCRIPTIONS.get(label, ""),
                    "confidence": round(float(score), 6),
                }
            )
        return {
            "text": clean_text,
            "intent": candidates[0]["label"],
            "description": candidates[0]["description"],
            "confidence": candidates[0]["confidence"],
            "candidates": candidates,
        }
