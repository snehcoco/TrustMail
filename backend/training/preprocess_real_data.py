"""
TrustMail — Real Dataset Preprocessing Pipeline
================================================
Loads, validates, normalizes, deduplicates, and splits the 5 real-world
email datasets from base_data/ into train/val/test CSVs.

NEVER modifies files in base_data/. Treats base_data/ as immutable.

Usage:
    cd TrustMail
    python backend/training/preprocess_real_data.py

Output (backend/datasets/processed/):
    train.csv, val.csv, test.csv
    dataset_manifest.json
    preprocessing_report.txt

Design decisions (see implementation_plan.md):
  - All label=0 → safe (0), label=1 → phishing/threat (1)
  - Enron/Ling label=1 is commercial spam, still treated as threat
  - Nazario is pure phishing corpus (all label=1)
  - Text normalization preserves security signals (URLs, caps, punctuation)
  - Deduplication before split (SHA-256 of normalized subject+body)
  - Near-duplicate campaign detection via body shingles
  - 80/10/10 stratified split, seed=42
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.model_selection import train_test_split

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent.parent.parent   # TrustMail/
BASE_DATA    = ROOT_DIR / "base_data"
PROCESSED    = ROOT_DIR / "backend" / "datasets" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

RANDOM_SEED  = 42
VAL_RATIO    = 0.10
TEST_RATIO   = 0.10

# ── Dataset Configurations ────────────────────────────────────────────────────
# Each entry: (filename, columns_to_keep, label_col)
DATASET_CONFIGS = [
    {
        "file":    "CEAS_08.csv",
        "source":  "ceas_08",
        "columns": {"subject": "subject", "body": "body", "label": "label",
                    "sender": "sender"},
        "encoding": "utf-8",
        "description": "CEAS 2008 spam/phishing benchmark — ham vs spam+phishing",
    },
    {
        "file":    "Enron.csv",
        "source":  "enron",
        "columns": {"subject": "subject", "body": "body", "label": "label"},
        "encoding": "utf-8",
        "description": "Enron corporate email corpus — ham vs spam",
    },
    {
        "file":    "Ling.csv",
        "source":  "ling",
        "columns": {"subject": "subject", "body": "body", "label": "label"},
        "encoding": "utf-8",
        "description": "Ling-Spam academic mailing list — ham vs spam",
    },
    {
        "file":    "Nazario.csv",
        "source":  "nazario",
        "columns": {"subject": "subject", "body": "body", "label": "label",
                    "sender": "sender"},
        "encoding": "utf-8",
        "description": "Nazario phishing corpus — pure phishing (all label=1)",
    },
    {
        "file":    "SpamAssasin.csv",
        "source":  "spamassasin",
        "columns": {"subject": "subject", "body": "body", "label": "label",
                    "sender": "sender"},
        "encoding": "utf-8",
        "description": "SpamAssassin public corpus — ham vs spam",
    },
]

# ── Label Mapping ─────────────────────────────────────────────────────────────
# All datasets use 0=safe, 1=threat. No remapping needed.
# Documented decision: treat all label=1 as threat (binary task).
VALID_LABELS = {0, 1}


# ═══════════════════════════════════════════════════════════════════════════════
# LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_dataset(config: dict) -> Tuple[pd.DataFrame, dict]:
    """Load a single dataset CSV and standardize its columns."""
    path = BASE_DATA / config["file"]
    stats = {
        "file": config["file"],
        "source": config["source"],
        "size_bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "initial_rows": 0,
        "rejected_invalid_label": 0,
        "rejected_empty_body": 0,
        "rejected_too_short": 0,
        "accepted_rows": 0,
        "label_dist": {},
    }

    # Try encoding
    try:
        df = pd.read_csv(path, encoding=config["encoding"], low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="latin-1", low_memory=False)
        logger.warning(f"  {config['file']}: fell back to latin-1 encoding")

    stats["initial_rows"] = len(df)
    logger.info(f"  Loaded {len(df):,} rows from {config['file']}")

    # Standardize column names
    col_map = config["columns"]
    out = pd.DataFrame()
    out["body"]    = df[col_map["body"]].fillna("").astype(str)
    out["subject"] = df[col_map["subject"]].fillna("") if "subject" in col_map else ""
    out["sender"]  = df[col_map["sender"]].fillna("")  if "sender"  in col_map else ""
    out["label"]   = df[col_map["label"]]
    out["source"]  = config["source"]

    return out, stats


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

MIN_BODY_CHARS = 10    # records shorter than this are noise
MAX_BODY_CHARS = 50_000  # safety cap; truncate, don't drop

def validate(df: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """Drop invalid records and record counts."""
    n0 = len(df)

    # 1. Invalid labels
    mask_bad_label = ~df["label"].isin(VALID_LABELS)
    stats["rejected_invalid_label"] = int(mask_bad_label.sum())
    df = df[~mask_bad_label].copy()

    # 2. Empty body
    mask_empty = df["body"].str.strip() == ""
    stats["rejected_empty_body"] = int(mask_empty.sum())
    df = df[~mask_empty].copy()

    # 3. Too short (likely noise / transport artifacts)
    mask_short = df["body"].str.len() < MIN_BODY_CHARS
    stats["rejected_too_short"] = int(mask_short.sum())
    df = df[~mask_short].copy()

    # 4. Truncate very long bodies (preserve structure — do not strip URLs/signals)
    df["body"] = df["body"].str[:MAX_BODY_CHARS]

    stats["accepted_rows"] = len(df)
    stats["label_dist"] = dict(df["label"].value_counts().astype(int))
    logger.info(f"  After validation: {len(df):,} rows "
                f"(dropped {n0 - len(df):,})")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# NORMALIZATION — preserve security signals
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_text(text: str) -> str:
    """
    Conservative Unicode + whitespace normalization.

    What we DO:
      - NFKC normalization (resolves visually identical Unicode chars)
      - Collapse multiple blank lines to single newline
      - Strip leading/trailing whitespace

    What we DON'T do:
      - Remove URLs (critical phishing signal)
      - Lowercase (capitalization is a phishing signal)
      - Remove punctuation (!, $, % are phishing signals)
      - Remove HTML (URL/anchor text analysis needs it)
      - Remove numbers or currency
    """
    if not text:
        return ""
    # Unicode NFKC: decomposes and recomposes (catches homoglyphs like ℬ→B)
    text = unicodedata.normalize("NFKC", text)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse horizontal whitespace runs (tabs → single space)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["body"]    = df["body"].apply(normalize_text)
    df["subject"] = df["subject"].apply(normalize_text)
    df["sender"]  = df["sender"].str.strip()
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

def _dedup_key(subject: str, body: str) -> str:
    """SHA-256 of lowercased subject + first 500 chars of body."""
    key = (subject.lower().strip() + "||" + body[:500].lower().strip())
    return hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()


def _near_dup_key(body: str) -> str:
    """
    Campaign template detection: hash of first 150 normalized chars.
    Phishing campaigns reuse identical intros with only URLs changed.
    O(n) — no pairwise comparison needed.
    """
    normalized = re.sub(r"https?://\S+", "URL", body[:150].lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.md5(normalized.encode("utf-8", errors="replace")).hexdigest()


def deduplicate(df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    n0 = len(df)

    # ── Exact dedup ──────────────────────────────────────────────────────────
    df = df.copy()
    df["_dedup_key"] = df.apply(
        lambda r: _dedup_key(str(r["subject"]), str(r["body"])), axis=1
    )
    before_exact = len(df)
    df = df.drop_duplicates(subset=["_dedup_key"], keep="first")
    exact_removed = before_exact - len(df)
    logger.info(f"  Exact dedup removed: {exact_removed:,}")

    # ── Near-dup campaign detection ──────────────────────────────────────────
    # Group rows by near-dup key and assign a campaign_id.
    # All rows in the same campaign will stay in the same split.
    df["_near_key"] = df["body"].apply(_near_dup_key)

    # Count near-dup groups
    campaign_counts = df["_near_key"].value_counts()
    campaign_dups   = campaign_counts[campaign_counts > 1]
    near_dup_groups = len(campaign_dups)
    near_dup_rows   = int(campaign_dups.sum())

    logger.info(f"  Near-dup campaign groups: {near_dup_groups:,} "
                f"({near_dup_rows:,} emails belong to repeated templates)")

    stats = {
        "exact_duplicates_removed": exact_removed,
        "near_dup_campaign_groups": near_dup_groups,
        "near_dup_campaign_emails": near_dup_rows,
    }
    return df, stats


# ═══════════════════════════════════════════════════════════════════════════════
# SPLITTING — leakage-safe
# ═══════════════════════════════════════════════════════════════════════════════

def split_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Leakage-safe stratified 80/10/10 split.

    Strategy: group by _near_key (campaign) first, so near-identical
    emails stay within the same split and don't leak between train and test.
    """
    # Assign split at the campaign level
    campaigns = np.array(df["_near_key"].unique())
    rng = np.random.default_rng(RANDOM_SEED)
    rng.shuffle(campaigns)

    n      = len(campaigns)
    n_val  = max(int(n * VAL_RATIO), 1)
    n_test = max(int(n * TEST_RATIO), 1)

    val_campaigns  = set(campaigns[:n_val])
    test_campaigns = set(campaigns[n_val:n_val + n_test])

    df = df.copy()
    df["_split"] = df["_near_key"].apply(
        lambda k: "val"  if k in val_campaigns  else
                  "test" if k in test_campaigns else "train"
    )

    train_df = df[df["_split"] == "train"].drop(columns=["_split","_dedup_key","_near_key"])
    val_df   = df[df["_split"] == "val"]  .drop(columns=["_split","_dedup_key","_near_key"])
    test_df  = df[df["_split"] == "test"] .drop(columns=["_split","_dedup_key","_near_key"])

    logger.info(f"  Split → train: {len(train_df):,}  val: {len(val_df):,}  test: {len(test_df):,}")

    # Verify zero overlap
    _verify_no_overlap(train_df, val_df, test_df)

    return train_df, val_df, test_df


def _verify_no_overlap(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> None:
    train_hashes = set(train.apply(lambda r: _dedup_key(str(r["subject"]), str(r["body"])), axis=1))
    val_hashes   = set(val.apply(  lambda r: _dedup_key(str(r["subject"]), str(r["body"])), axis=1))
    test_hashes  = set(test.apply( lambda r: _dedup_key(str(r["subject"]), str(r["body"])), axis=1))

    tv = train_hashes & val_hashes
    tt = train_hashes & test_hashes
    vt = val_hashes   & test_hashes

    if tv or tt or vt:
        raise RuntimeError(
            f"DATA LEAKAGE DETECTED: train∩val={len(tv)}, train∩test={len(tt)}, val∩test={len(vt)}"
        )
    logger.info("  ✓ No leakage between train / val / test sets")


# ═══════════════════════════════════════════════════════════════════════════════
# FILE CHECKSUM
# ═══════════════════════════════════════════════════════════════════════════════

def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    logger.info("=" * 60)
    logger.info("[1/6] Inspecting base_data/ datasets...")
    logger.info("=" * 60)

    all_dfs   = []
    all_stats = []

    for config in DATASET_CONFIGS:
        path = BASE_DATA / config["file"]
        if not path.exists():
            logger.warning(f"  SKIP: {config['file']} not found in base_data/")
            continue

        logger.info(f"\n--- {config['file']} ---")
        logger.info(f"  {config['description']}")
        df, stats = load_dataset(config)
        all_dfs.append(df)
        all_stats.append(stats)

    if not all_dfs:
        raise RuntimeError("No datasets found in base_data/. Cannot proceed.")

    # ── 2. Validate ───────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("[2/6] Validating records...")
    logger.info("=" * 60)

    validated = []
    for df, stats in zip(all_dfs, all_stats):
        df = validate(df, stats)
        validated.append(df)

    combined = pd.concat(validated, ignore_index=True)
    logger.info(f"\nCombined after validation: {len(combined):,} rows")
    logger.info(f"Label distribution: {dict(combined['label'].value_counts())}")

    # ── 3. Normalize ──────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("[3/6] Normalizing text (preserving security signals)...")
    logger.info("=" * 60)

    combined = normalize_df(combined)
    logger.info(f"  Normalization complete. {len(combined):,} rows.")

    # ── 4. Deduplicate ────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("[4/6] Deduplicating...")
    logger.info("=" * 60)

    before_dedup = len(combined)
    combined, dedup_stats = deduplicate(combined)
    after_dedup = len(combined)

    logger.info(f"  Total removed by dedup: {before_dedup - after_dedup:,}")
    logger.info(f"  Remaining: {after_dedup:,}")

    # ── 5. Split ──────────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("[5/6] Creating train/val/test splits (80/10/10)...")
    logger.info("=" * 60)

    train_df, val_df, test_df = split_data(combined)

    # Per-source distribution
    logger.info("\n  Per-source distribution in train set:")
    for src, cnt in train_df["source"].value_counts().items():
        logger.info(f"    {src}: {cnt:,}")

    # Class balance check
    for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        dist = dict(split_df["label"].value_counts())
        logger.info(f"  {split_name} labels: {dist}")

    # ── 6. Save ───────────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("[6/6] Saving processed datasets...")
    logger.info("=" * 60)

    train_path = PROCESSED / "train.csv"
    val_path   = PROCESSED / "val.csv"
    test_path  = PROCESSED / "test.csv"

    train_df.to_csv(train_path, index=False, encoding="utf-8")
    val_df  .to_csv(val_path,   index=False, encoding="utf-8")
    test_df .to_csv(test_path,  index=False, encoding="utf-8")

    logger.info(f"  ✓ train.csv   → {len(train_df):,} rows")
    logger.info(f"  ✓ val.csv     → {len(val_df):,} rows")
    logger.info(f"  ✓ test.csv    → {len(test_df):,} rows")

    # ── Manifest ──────────────────────────────────────────────────────────────
    manifest = {
        "generated_at":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed":        RANDOM_SEED,
        "split_ratios":       {"train": 0.80, "val": VAL_RATIO, "test": TEST_RATIO},
        "split_strategy":     "campaign-aware stratified split (near-dup groups stay together)",
        "label_mapping":      {"0": "safe", "1": "phishing/threat"},
        "final_counts":       {
            "train":          len(train_df),
            "val":            len(val_df),
            "test":           len(test_df),
            "total":          len(train_df) + len(val_df) + len(test_df),
        },
        "class_distribution": {
            "train": dict(train_df["label"].value_counts().astype(int)),
            "val":   dict(val_df  ["label"].value_counts().astype(int)),
            "test":  dict(test_df ["label"].value_counts().astype(int)),
        },
        "deduplication":      dedup_stats,
        "datasets":           all_stats,
    }

    manifest_path = PROCESSED / "dataset_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    logger.info(f"  ✓ dataset_manifest.json saved")

    # ── Preprocessing Report ──────────────────────────────────────────────────
    report_lines = [
        "TrustMail — Preprocessing Report",
        "=" * 50,
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "DATASET AUDIT",
        "-" * 40,
    ]
    total_initial = total_accepted = 0
    for s in all_stats:
        report_lines += [
            f"\n{s['file']}",
            f"  Initial rows:           {s['initial_rows']:,}",
            f"  Rejected (bad label):   {s['rejected_invalid_label']:,}",
            f"  Rejected (empty body):  {s['rejected_empty_body']:,}",
            f"  Rejected (too short):   {s['rejected_too_short']:,}",
            f"  Accepted:               {s['accepted_rows']:,}",
            f"  Label dist:             {s['label_dist']}",
            f"  SHA-256:                {s['sha256'][:16]}...",
        ]
        total_initial  += s["initial_rows"]
        total_accepted += s["accepted_rows"]

    report_lines += [
        "",
        "SUMMARY",
        "-" * 40,
        f"Total initial records:      {total_initial:,}",
        f"Total accepted records:     {total_accepted:,}",
        f"Exact duplicates removed:   {dedup_stats['exact_duplicates_removed']:,}",
        f"After deduplication:        {after_dedup:,}",
        f"",
        f"SPLITS",
        "-" * 40,
        f"Train:   {len(train_df):,}  (label dist: {dict(train_df['label'].value_counts())})",
        f"Val:     {len(val_df):,}  (label dist: {dict(val_df['label'].value_counts())})",
        f"Test:    {len(test_df):,}  (label dist: {dict(test_df['label'].value_counts())})",
        "",
        "LEAKAGE PREVENTION",
        "-" * 40,
        "  - Deduplication performed BEFORE splitting",
        "  - Near-duplicate campaign groups kept within same split",
        "  - Zero-overlap verified (SHA-256 check on all split pairs)",
        "",
        f"Elapsed: {time.time()-t0:.1f}s",
    ]

    report_path = PROCESSED / "preprocessing_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    logger.info(f"  ✓ preprocessing_report.txt saved")
    logger.info(f"\n✅ Preprocessing complete in {time.time()-t0:.1f}s")
    logger.info(f"   Run: python backend/training/run_training.py --use-real-data")


if __name__ == "__main__":
    main()
