# TrustMail — Model Training Report

**Generated:** 2026-08-01 18:41:05  
**Data source:** real_datasets  
**Random seed:** 42

---

## Dataset Summary

| Split | Samples |
|---|---|
| Train | 60,442 |
| Validation | 7,536 |
| Test | 7,377 |
| **Total** | **75,355** |

---

## Individual Model Validation Metrics

| Model | AUC | PR-AUC | F1 | Precision | Recall | FPR |
|---|---|---|---|---|---|---|
| logistic_regression | 0.89325 | 0.89007 | 0.80773 | 0.81201 | 0.80349 | 0.18962 |
| random_forest | 0.97995 | 0.98116 | 0.92181 | 0.9447 | 0.9 | 0.09319 |
| xgboost | 0.98184 | 0.98362 | 0.93207 | 0.94036 | 0.92392 | 0.07292 |
| lightgbm | 0.97755 | 0.97927 | 0.91993 | 0.93212 | 0.90806 | 0.08742 |
| catboost | 0.97751 | 0.97929 | 0.92155 | 0.93401 | 0.90941 | 0.0861 |

> **Best individual model (by AUC):** xgboost

---

## Ensemble Test Set Results

| Metric | Value |
|---|---|
| ROC-AUC | 0.98186 |
| PR-AUC | 0.98042 |
| F1 | 0.92248 |
| Precision | 0.92857 |
| Recall | 0.91647 |
| Accuracy | 0.92951 |
| False Positive Rate | 0.05949 |
| False Negative Rate | 0.08353 |

## Confusion Matrix (Test Set)

| | Predicted Safe | Predicted Phishing |
|---|---|---|
| **Actual Safe** | 3,763 (TN) | 238 (FP) |
| **Actual Phishing** | 282 (FN) | 3,094 (TP) |

---

## Ensemble Weights

| Model | Weight |
|---|---|
| random_forest | 0.3 |
| xgboost | 0.28 |
| lightgbm | 0.22 |
| catboost | 0.12 |
| logistic_regression | 0.08 |

---

## Label Mapping

| Dataset | label=0 | label=1 |
|---|---|---|
| CEAS_08 | safe | phishing/spam |
| Enron | safe | spam (treated as threat) |
| Ling | safe | spam (treated as threat) |
| Nazario | — | phishing (all phishing) |
| SpamAssasin | safe | spam (treated as threat) |

---

## Limitations

- Enron and Ling label=1 is **commercial spam**, not targeted phishing.
  The model learns a safe vs threat boundary, which includes spam.
- Datasets span 2001–2008. Modern spear-phishing and BEC tactics may not be well-represented.
- No attachment content, no HTML rendering, no DNS/WHOIS resolution.
- Performance on the synthetic prior test will be much lower than on the real test set — this is expected.