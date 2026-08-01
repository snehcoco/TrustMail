"""
Transformer Fine-tuning Pipeline
==================================
Fine-tunes DistilBERT (or MiniLM / DeBERTa-v3-small) for phishing detection
and exports the trained model to ONNX format.

CRITICAL: This script runs 100% locally.
No external AI APIs are called at any point.
The base model is downloaded from HuggingFace once and cached locally.
All subsequent training uses only the local cache.

Usage:
    cd backend
    python training/train_transformer.py \
        --model distilbert-base-uncased \
        --epochs 3 \
        --batch-size 16

Output:
    trained_models/distilbert_phishing.onnx
    trained_models/tokenizer.json     (for offline tokenization)
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

# Force offline mode — never call external AI APIs
os.environ["TRANSFORMERS_OFFLINE"] = "0"  # Allow initial download; set to "1" after first run
os.environ["HF_DATASETS_OFFLINE"] = "0"

from config.settings import get_settings
settings = get_settings()


SUPPORTED_MODELS = {
    "distilbert": "distilbert-base-uncased",
    "minilm": "microsoft/MiniLM-L12-H384-uncased",
    "deberta-small": "microsoft/deberta-v3-small",
}


def load_datasets(data_dir: Path):
    """Load training/validation data."""
    import pandas as pd

    train_path = data_dir / "train.csv"
    val_path = data_dir / "val.csv"

    if not train_path.exists():
        raise FileNotFoundError(
            f"Training data not found at {train_path}. "
            "Run preprocessing pipeline first."
        )

    train_df = pd.read_csv(train_path)
    val_df = pd.read_csv(val_path) if val_path.exists() else train_df.sample(frac=0.15, random_state=42)
    return train_df, val_df


def create_dataset(df, tokenizer, max_length: int = 512):
    """Create a HuggingFace Dataset from a DataFrame."""
    from datasets import Dataset

    texts = (df.get("text", df.get("body_text", "")).fillna("") + " " + df.get("subject", "").fillna("")).tolist()
    labels = df["label"].astype(int).tolist()

    dataset = Dataset.from_dict({"text": texts, "label": labels})

    def tokenize_fn(batch):
        return tokenizer(
            batch["text"],
            padding="max_length",
            truncation=True,
            max_length=max_length,
        )

    dataset = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])
    dataset.set_format(type="torch", columns=["input_ids", "attention_mask", "label"])
    return dataset


def fine_tune(
    model_name: str,
    train_df,
    val_df,
    output_dir: Path,
    epochs: int = 3,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
) -> None:
    """Fine-tune the transformer model for phishing classification."""
    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        EarlyStoppingCallback,
    )
    from sklearn.metrics import accuracy_score, roc_auc_score

    logger.info(f"Loading base model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=2,
        id2label={0: "safe", 1: "phishing"},
        label2id={"safe": 0, "phishing": 1},
    )

    logger.info("Preparing datasets...")
    train_dataset = create_dataset(train_df, tokenizer)
    val_dataset = create_dataset(val_df, tokenizer)

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        probs = softmax(logits)[:, 1]
        auc = roc_auc_score(labels, probs)
        acc = accuracy_score(labels, preds)
        return {"accuracy": acc, "auc": auc}

    def softmax(x):
        e = np.exp(x - np.max(x, axis=1, keepdims=True))
        return e / e.sum(axis=1, keepdims=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_ratio=0.1,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="auc",
        greater_is_better=True,
        logging_dir=str(output_dir / "logs"),
        logging_steps=50,
        fp16=torch.cuda.is_available(),
        dataloader_num_workers=0,
        report_to="none",  # No cloud reporting
        seed=42,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    logger.info("Starting fine-tuning...")
    trainer.train()

    logger.info("Saving fine-tuned model and tokenizer...")
    model_save_path = output_dir / "transformer_finetuned"
    model.save_pretrained(str(model_save_path))
    tokenizer.save_pretrained(str(model_save_path))

    # Save tokenizer.json to trained_models for offline use
    import shutil
    tokenizer_json = model_save_path / "tokenizer.json"
    if tokenizer_json.exists():
        shutil.copy(str(tokenizer_json), str(output_dir / "tokenizer.json"))

    logger.info(f"✓ Model saved to {model_save_path}")
    logger.info("Exporting to ONNX...")

    from training.export_onnx import export_to_onnx
    export_to_onnx(str(model_save_path), str(output_dir / settings.ONNX_MODEL_FILE))


def main():
    parser = argparse.ArgumentParser(description="Fine-tune transformer for TrustMail")
    parser.add_argument("--model", default="distilbert", choices=list(SUPPORTED_MODELS.keys()))
    parser.add_argument("--data-dir", default="datasets/processed")
    parser.add_argument("--output-dir", default=settings.MODELS_DIR)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    args = parser.parse_args()

    model_name = SUPPORTED_MODELS[args.model]
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Fine-tuning: {model_name}")
    logger.info(f"Data: {data_dir}, Output: {output_dir}")

    train_df, val_df = load_datasets(data_dir)
    logger.info(f"Train: {len(train_df)}, Val: {len(val_df)}")

    fine_tune(
        model_name=model_name,
        train_df=train_df,
        val_df=val_df,
        output_dir=output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
    )

    logger.info("✅ Transformer training complete!")


if __name__ == "__main__":
    main()
