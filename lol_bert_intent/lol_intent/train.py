from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup


@dataclass
class Example:
    text: str
    label: str


class IntentDataset(Dataset):
    def __init__(self, examples: list[Example], tokenizer, label2id: dict[str, int], max_length: int):
        self.examples = examples
        self.tokenizer = tokenizer
        self.label2id = label2id
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        item = self.examples[index]
        encoded = self.tokenizer(
            item.text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        return {
            "input_ids": encoded["input_ids"].squeeze(0),
            "attention_mask": encoded["attention_mask"].squeeze(0),
            "labels": torch.tensor(self.label2id[item.label], dtype=torch.long),
        }


def read_csv(path: Path) -> list[Example]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "text" not in reader.fieldnames or "label" not in reader.fieldnames:
            raise ValueError("CSV must contain columns: text,label")
        rows = [Example(row["text"].strip(), row["label"].strip()) for row in reader]
    rows = [row for row in rows if row.text and row.label]
    if len(rows) < 20:
        raise ValueError("Need at least 20 labeled rows. More is strongly recommended.")
    return rows


def evaluate(model, loader: DataLoader, device: torch.device, id2label: dict[int, str]) -> dict:
    model.eval()
    all_preds: list[int] = []
    all_labels: list[int] = []
    total_loss = 0.0
    with torch.no_grad():
        for batch in loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**batch)
            total_loss += outputs.loss.item()
            preds = outputs.logits.argmax(dim=-1)
            all_preds.extend(preds.cpu().tolist())
            all_labels.extend(batch["labels"].cpu().tolist())
    target_names = [id2label[i] for i in sorted(id2label)]
    report = classification_report(
        all_labels,
        all_preds,
        labels=list(sorted(id2label)),
        target_names=target_names,
        output_dict=True,
        zero_division=0,
    )
    report["loss"] = total_loss / max(len(loader), 1)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune BERT for LOL intent classification on CPU.")
    parser.add_argument("--data", default="data/intents_binary.csv", help="CSV file with text,label columns.")
    parser.add_argument("--model-name", default="bert-base-chinese", help="HuggingFace model name or local path.")
    parser.add_argument("--output-dir", default="models/lol-bert-binary-intent", help="Where to save the fine-tuned model.")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=96)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    data_path = Path(args.data)
    examples = read_csv(data_path)
    labels = sorted({example.label for example in examples})
    label2id = {label: idx for idx, label in enumerate(labels)}
    id2label = {idx: label for label, idx in label2id.items()}

    train_rows, val_rows = train_test_split(
        examples,
        test_size=args.test_size,
        random_state=args.seed,
        stratify=[example.label for example in examples],
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=len(labels),
        id2label={str(k): v for k, v in id2label.items()},
        label2id=label2id,
    )

    device = torch.device("cpu")
    model.to(device)

    train_loader = DataLoader(
        IntentDataset(train_rows, tokenizer, label2id, args.max_length),
        batch_size=args.batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        IntentDataset(val_rows, tokenizer, label2id, args.max_length),
        batch_size=args.batch_size,
        shuffle=False,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(total_steps // 10, 1),
        num_training_steps=total_steps,
    )

    best_f1 = -1.0
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        for batch in train_loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            optimizer.zero_grad()
            outputs = model(**batch)
            outputs.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            running_loss += outputs.loss.item()

        metrics = evaluate(model, val_loader, device, id2label)
        macro_f1 = metrics["macro avg"]["f1-score"]
        print(
            f"epoch={epoch} train_loss={running_loss / max(len(train_loader), 1):.4f} "
            f"val_loss={metrics['loss']:.4f} macro_f1={macro_f1:.4f}"
        )
        if macro_f1 > best_f1:
            best_f1 = macro_f1
            model.save_pretrained(output_dir)
            tokenizer.save_pretrained(output_dir)
            (output_dir / "labels.json").write_text(
                json.dumps({"label2id": label2id, "id2label": id2label}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (output_dir / "eval_report.json").write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"saved best model to {output_dir} macro_f1={best_f1:.4f}")


if __name__ == "__main__":
    main()
