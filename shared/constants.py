"""
Shared Constants (Python version for backend)
"""

RISK_LEVELS = ["safe", "low_risk", "suspicious", "phishing", "highly_dangerous"]

RISK_THRESHOLDS = {
    "safe": 0.0,
    "low_risk": 0.20,
    "suspicious": 0.45,
    "phishing": 0.65,
    "highly_dangerous": 0.85,
}

SUPPORTED_PLATFORMS = ["gmail", "outlook", "yahoo", "protonmail", "outlook365"]

API_VERSION = "1.0.0"
MODEL_VERSION = "1.0.0"

MAX_EMAIL_BODY_LENGTH = 50_000
MAX_URLS_PER_EMAIL = 100

DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".js",
    ".jar", ".hta", ".scr", ".pif", ".reg", ".msi", ".dll",
    ".lnk", ".wsf", ".wsh",
}

FREE_EMAIL_PROVIDERS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "icloud.com", "protonmail.com", "mail.com",
}
