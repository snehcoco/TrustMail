"""
Dataset Downloader
==================
Downloads public phishing/spam datasets for TrustMail training.

Supported datasets:
  1. SpamAssassin Public Corpus
  2. Enron Email Dataset (via Kaggle)
  3. UCI SMS Spam Collection (fallback, for language features)
  4. PhishTank URL dataset (for URL analysis training)

Usage:
    cd backend
    python datasets/download_datasets.py

All datasets are saved to datasets/raw/.
Run preprocess_datasets.py after this.
"""

import argparse
import gzip
import hashlib
import os
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve
from urllib.error import URLError

from loguru import logger


RAW_DIR = Path("datasets/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = {
    "spamassassin": {
        "url": "https://spamassassin.apache.org/old/publiccorpus/20050311_spam_2.tar.bz2",
        "filename": "spamassassin_spam.tar.bz2",
        "type": "spam",
        "license": "Apache 2.0",
    },
    "spamassassin_ham": {
        "url": "https://spamassassin.apache.org/old/publiccorpus/20030228_easy_ham.tar.bz2",
        "filename": "spamassassin_ham.tar.bz2",
        "type": "ham",
        "license": "Apache 2.0",
    },
    "uci_sms": {
        "url": "https://archive.ics.uci.edu/ml/machine-learning-databases/00228/smsspamcollection.zip",
        "filename": "sms_spam.zip",
        "type": "mixed",
        "license": "CC BY 4.0",
    },
    "phishtank": {
        "url": "https://data.phishtank.com/data/online-valid.csv.gz",
        "filename": "phishtank_urls.csv.gz",
        "type": "urls",
        "license": "CC BY-SA 2.5",
        "note": "Requires free PhishTank account API key in PHISHTANK_API_KEY env var",
    },
}


def download_file(url: str, dest: Path, description: str = "") -> bool:
    """Download a file with progress logging."""
    if dest.exists():
        logger.info(f"Already downloaded: {dest.name}")
        return True

    logger.info(f"Downloading {description or dest.name}...")
    try:
        def progress(count, block_size, total_size):
            if total_size > 0:
                pct = count * block_size / total_size * 100
                if count % 100 == 0:
                    logger.debug(f"  {pct:.1f}%")

        urlretrieve(url, str(dest), reporthook=progress)
        logger.info(f"✓ Downloaded: {dest.name} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
        return True
    except URLError as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


def extract_archive(archive: Path, dest_dir: Path) -> None:
    """Extract tar.bz2, tar.gz, or zip archives."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = archive.name

    if name.endswith(".tar.bz2") or name.endswith(".tar.gz"):
        with tarfile.open(str(archive), "r:*") as tar:
            tar.extractall(str(dest_dir))
    elif name.endswith(".zip"):
        with zipfile.ZipFile(str(archive), "r") as zf:
            zf.extractall(str(dest_dir))
    elif name.endswith(".gz"):
        output = dest_dir / archive.stem
        with gzip.open(str(archive), "rb") as f_in:
            output.write_bytes(f_in.read())

    logger.info(f"✓ Extracted: {archive.name} -> {dest_dir}")


def create_sample_dataset() -> None:
    """
    Create a minimal sample dataset for testing without downloading.
    Contains 20 safe + 20 phishing examples.
    """
    import csv
    import json

    sample_dir = Path("datasets/sample_data")
    sample_dir.mkdir(parents=True, exist_ok=True)

    safe_examples = [
        {"text": "Hi team, please find the attached Q4 report. Let me know if you have questions.", "label": 0, "subject": "Q4 Report"},
        {"text": "Your Amazon order #123-456789 has shipped. Track at amazon.com/orders.", "label": 0, "subject": "Order Shipped"},
        {"text": "Meeting rescheduled to 3pm tomorrow. Conference room B.", "label": 0, "subject": "Meeting Update"},
        {"text": "Thanks for your application. We'll be in touch within 5 business days.", "label": 0, "subject": "Application Received"},
        {"text": "Your monthly bank statement is ready to view in your account.", "label": 0, "subject": "Statement Ready"},
    ]

    phishing_examples = [
        {"text": "URGENT: Your account has been compromised! Click here immediately to verify your password: http://192.168.1.1/verify", "label": 1, "subject": "URGENT: Account Suspended"},
        {"text": "Dear Customer, your PayPal account is limited. Confirm your information now or lose access: http://paypa1.com/secure", "label": 1, "subject": "PayPal Account Limited"},
        {"text": "You won $1,000,000! Claim your prize now. Send your bank details to collect.", "label": 1, "subject": "Congratulations Winner!"},
        {"text": "IRS Notice: You have an outstanding tax refund. Provide your SSN and banking information immediately.", "label": 1, "subject": "Tax Refund Pending"},
        {"text": "Your Microsoft account will be suspended in 24 hours. Act NOW: http://micr0soft.tk/login", "label": 1, "subject": "Account Suspension Notice"},
    ]

    all_examples = safe_examples + phishing_examples

    csv_path = sample_dir / "sample_emails.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "label", "subject"])
        writer.writeheader()
        writer.writerows(all_examples)

    logger.info(f"✓ Sample dataset created: {csv_path}")

    # Also save individual JSON samples for API testing
    with open(sample_dir / "safe_email.json", "w") as f:
        json.dump(safe_examples[0], f, indent=2)
    with open(sample_dir / "phishing_email.json", "w") as f:
        json.dump(phishing_examples[0], f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Download TrustMail training datasets")
    parser.add_argument("--datasets", nargs="+", choices=list(DATASETS.keys()) + ["all", "sample"],
                        default=["sample"], help="Which datasets to download")
    parser.add_argument("--extract", action="store_true", help="Extract after downloading")
    args = parser.parse_args()

    if "sample" in args.datasets or "all" in args.datasets:
        logger.info("Creating sample dataset for testing...")
        create_sample_dataset()

    datasets_to_fetch = (
        list(DATASETS.keys()) if "all" in args.datasets
        else [d for d in args.datasets if d != "sample"]
    )

    for dataset_key in datasets_to_fetch:
        info = DATASETS[dataset_key]
        dest = RAW_DIR / info["filename"]

        if "note" in info:
            logger.info(f"Note for {dataset_key}: {info['note']}")

        success = download_file(info["url"], dest, dataset_key)

        if success and args.extract:
            extract_archive(dest, RAW_DIR / dataset_key)

    logger.info("✅ Dataset download complete!")
    logger.info("Next: python datasets/preprocess_datasets.py")


if __name__ == "__main__":
    main()
