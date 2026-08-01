"""
Dataset Preprocessor
=====================
Processes raw downloaded datasets into a unified train/val/test CSV format.

Handles:
  - SpamAssassin corpus (.eml files)
  - Enron dataset (directory structure)
  - UCI SMS spam (tab-separated)
  - Custom JSON datasets

Output format:
    datasets/processed/train.csv  (70%)
    datasets/processed/val.csv    (15%)
    datasets/processed/test.csv   (15%)

Each CSV has columns: text, subject, sender, label
Where label: 0=safe, 1=phishing/spam

Usage:
    cd backend
    python datasets/preprocess_datasets.py
"""

import email
import hashlib
import os
import re
import sys
from email import policy
from pathlib import Path

import pandas as pd
from loguru import logger
from sklearn.model_selection import train_test_split
from sklearn.utils import resample

sys.path.insert(0, str(Path(__file__).parent.parent))
from preprocessing.text_cleaner import TextCleaner


RAW_DIR = Path("datasets/raw")
PROCESSED_DIR = Path("datasets/processed")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

cleaner = TextCleaner()


def parse_eml_file(path: Path) -> dict:
    """Parse a .eml file and extract text, subject, and sender."""
    try:
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        subject = str(msg.get("subject", ""))
        sender = str(msg.get("from", ""))

        # Extract text body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    body = part.get_content()
                    break
                elif ctype == "text/html" and not body:
                    body = cleaner.extract_text_from_html(part.get_content())
        else:
            body = msg.get_content()

        return {
            "text": cleaner.clean(body),
            "subject": cleaner.clean_subject(subject),
            "sender": sender,
        }
    except Exception as e:
        return {"text": "", "subject": "", "sender": ""}


def process_spamassassin(raw_dir: Path) -> pd.DataFrame:
    """Process SpamAssassin corpus."""
    records = []

    for label_dir, label in [("spam", 1), ("easy_ham", 0), ("hard_ham", 0)]:
        dir_path = raw_dir / label_dir
        if not dir_path.exists():
            continue

        files = list(dir_path.glob("*"))
        logger.info(f"Processing SpamAssassin {label_dir}: {len(files)} files")

        for fp in files:
            if fp.is_file():
                parsed = parse_eml_file(fp)
                if parsed["text"] or parsed["subject"]:
                    parsed["label"] = label
                    records.append(parsed)

    return pd.DataFrame(records)


def process_uci_sms(raw_dir: Path) -> pd.DataFrame:
    """Process UCI SMS Spam Collection."""
    sms_path = raw_dir / "SMSSpamCollection"
    if not sms_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(sms_path, sep="\t", header=None, names=["label_str", "text"])
    df["label"] = (df["label_str"] == "spam").astype(int)
    df["subject"] = ""
    df["sender"] = ""
    df["text"] = df["text"].apply(lambda t: cleaner.clean(t))
    return df[["text", "subject", "sender", "label"]]


def process_sample_data() -> pd.DataFrame:
    """Load the sample dataset created by download_datasets.py."""
    sample_path = Path("datasets/sample_data/sample_emails.csv")
    if not sample_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(sample_path)
    df["sender"] = ""
    return df[["text", "subject", "sender", "label"]]


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate emails based on text hash."""
    df["_hash"] = df["text"].apply(lambda t: hashlib.md5(t.encode()).hexdigest())
    original_len = len(df)
    df = df.drop_duplicates(subset=["_hash"]).drop(columns=["_hash"])
    logger.info(f"Deduplication: {original_len} -> {len(df)} ({original_len - len(df)} removed)")
    return df


def balance_classes(df: pd.DataFrame) -> pd.DataFrame:
    """Oversample minority class to achieve rough balance."""
    counts = df["label"].value_counts()
    logger.info(f"Before balancing: {dict(counts)}")

    majority = df[df["label"] == counts.idxmax()]
    minority = df[df["label"] == counts.idxmin()]

    minority_upsampled = resample(
        minority,
        replace=True,
        n_samples=len(majority),
        random_state=42,
    )

    balanced = pd.concat([majority, minority_upsampled]).sample(frac=1, random_state=42)
    logger.info(f"After balancing: {dict(balanced['label'].value_counts())}")
    return balanced


def main():
    all_dataframes = []

    # 1. SpamAssassin
    spamassassin_dir = RAW_DIR / "spamassassin"
    if spamassassin_dir.exists():
        df = process_spamassassin(spamassassin_dir)
        if not df.empty:
            logger.info(f"SpamAssassin: {len(df)} examples")
            all_dataframes.append(df)

    # 2. UCI SMS
    df_sms = process_uci_sms(RAW_DIR)
    if not df_sms.empty:
        logger.info(f"UCI SMS: {len(df_sms)} examples")
        all_dataframes.append(df_sms)

    # 3. Sample data (always include)
    df_sample = process_sample_data()
    if not df_sample.empty:
        logger.info(f"Sample data: {len(df_sample)} examples")
        all_dataframes.append(df_sample)

    if not all_dataframes:
        logger.error("No data found! Run download_datasets.py first.")
        return

    # Combine all sources
    df = pd.concat(all_dataframes, ignore_index=True)
    df = df.dropna(subset=["text"])
    df = df[df["text"].str.len() > 10]  # Remove near-empty rows

    # Deduplicate and balance
    df = deduplicate(df)
    df = balance_classes(df)

    # Train / val / test split
    train_df, temp_df = train_test_split(df, test_size=0.30, random_state=42, stratify=df["label"])
    val_df, test_df = train_test_split(temp_df, test_size=0.50, random_state=42, stratify=temp_df["label"])

    # Save
    train_df.to_csv(PROCESSED_DIR / "train.csv", index=False)
    val_df.to_csv(PROCESSED_DIR / "val.csv", index=False)
    test_df.to_csv(PROCESSED_DIR / "test.csv", index=False)

    logger.info(f"✓ Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")
    logger.info(f"Saved to {PROCESSED_DIR}/")
    logger.info("✅ Preprocessing complete!")
    logger.info("Next: python training/train_classical.py")


if __name__ == "__main__":
    main()
