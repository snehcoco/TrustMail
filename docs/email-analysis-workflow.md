# TrustMail — Email Analysis Workflow

## Complete Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                       EMAIL LIFECYCLE                        │
│                                                             │
│  1. Inbox View         2. Lightweight Scan                  │
│  ┌──────────────┐     ┌─────────────────────────────┐      │
│  │ Email row    │────►│ subject + sender only        │      │
│  │ appears in  │     │ → backend → risk pill shown  │      │
│  │ inbox list  │     └─────────────────────────────┘      │
│  └──────┬───────┘                                           │
│         │ User clicks row                                   │
│         ▼                                                   │
│  3. Email Opens        4. Full AI Analysis                  │
│  ┌──────────────┐     ┌─────────────────────────────┐      │
│  │ Full email   │────►│ subject + body + URLs +      │      │
│  │ DOM loaded  │     │ headers → 4-stage pipeline  │      │
│  └──────┬───────┘     └──────────────┬───────────────┘     │
│         │                            │                      │
│         ▼                            ▼                      │
│  5. Badge Shown        6. Popup Report                      │
│  ┌──────────────┐     ┌─────────────────────────────┐      │
│  │ Floating      │     │ Risk meter, confidence,     │      │
│  │ risk badge  │     │ SHAP explanations, history  │      │
│  └──────────────┘     └─────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — Inbox Detection

**Trigger:** User navigates to inbox, scrolls, changes folders, or search results load.

**Implementation:** `content/inbox-scanner.js` + provider scripts

```
MutationObserver fires on DOM change
    └─ Queries provider-specific row selectors
         ├─ Gmail:      tr.zA
         ├─ Outlook:    div[role="option"]
         ├─ Yahoo:      li[data-test-id]
         └─ ProtonMail: div[data-element-id]
              │
              ▼
    WeakMap deduplication check (already processed? skip)
              │
              ▼
    Provider extractFn() called on row:
         returns { subject, sender, emailId, subjectEl }
              │
              ▼
    Pushed to scan queue (max 8 concurrent)
              │
              ▼
    Loading spinner pill injected into subjectEl
```

---

## Phase 2 — Lightweight Inbox Scan

**Trigger:** Job dequeued from inbox scan queue.

**Key difference from full scan:** Only `subject` and `sender` are sent. `bodyText` is intentionally empty string. This makes inbox scans ~10x faster.

```
requestIdleCallback fires (browser is idle)
    └─ chrome.runtime.sendMessage(ANALYZE_INBOX_ROW)
         └─ Service worker receives ANALYZE_INBOX_ROW
              └─ Calls analyzeEmail() with header-only payload
                   └─ Checks 5-min cache (cacheKey = sender::subject)
                        │ Cache hit → return cached result immediately
                        │ Cache miss →
                        ▼
               POST http://127.0.0.1:8000/api/v1/analyze
               {
                 "subject": "...",
                 "sender": "...",
                 "body_text": "",
                 "urls": [],
                 "platform": "gmail"
               }
                        │
                        ▼
               Feature extractor (header features only)
               Classical ensemble prediction
               Returns risk_level + risk_score + confidence
```

---

## Phase 3 — Risk Pill Injection

**Trigger:** Backend returns analysis result.

```
Response received by service worker
    └─ Returned to inbox-scanner.js via sendResponse callback
         └─ Loading pill replaced with result pill:
              ┌─────────────────────────────────────┐
              │ 🟢 12%  │  🟡 28%  │  🔴 78%        │
              │ Safe    │ Low Risk │ Phishing        │
              └─────────────────────────────────────┘
                   │
                   ├─ Hover → Tooltip shown:
                   │    Risk: Phishing (78%)
                   │    Confidence: 91%
                   │    Reasons:
                   │      › Suspicious sender domain
                   │      › Urgent credential request
                   │      › Reply-To mismatch
                   │
                   └─ Click → SET_POPUP_RESULT stored in chrome.storage
                              → User clicks TrustMail icon
                              → Popup loads stored result immediately
```

---

## Phase 4 — Full Email Analysis

**Trigger:** User clicks an email row to open it.

```
Content script detects email open:
  Gmail:      [data-message-id] attribute changes
  Outlook:    h1[aria-label="Message Subject"] appears
  Yahoo:      h1[data-test-id="message-subject"] appears
  ProtonMail: h1[data-testid="message:subject"] appears

    └─ Full DOM extraction:
         subject    → email subject line
         bodyText   → plain text (up to 50,000 chars)
         bodyHtml   → HTML content (up to 100,000 chars)
         sender     → From address
         senderDomain → domain extracted from sender
         replyTo    → Reply-To header value
         urls       → all href links found in body (up to 100)
              │
              ▼
    ANALYZE_EMAIL → service worker
              │
              ▼
    POST /api/v1/analyze (full payload)
```

---

## Phase 5 — Backend Processing Pipeline

```
FastAPI receives POST /api/v1/analyze
              │
              ▼
    Pydantic AnalyzeRequest validation
              │
              ▼
    EmailAnalyzer.analyze() called
              │
    ┌─────────┴─────────┐
    ▼                   ▼
Feature Extractor   URL Analyzer
(text + headers)    (per-URL scoring)
    │                   │
    └─────────┬─────────┘
              ▼
    ┌─────────────────┐
    │ Classical Ens.  │──── RandomForest
    │                 │──── XGBoost
    │                 │──── LightGBM
    │                 │──── CatBoost
    │                 │──── LogReg
    └─────────┬───────┘
              │
    ┌─────────▼───────┐
    │ ONNX Transformer│──── DistilBERT inference
    │ (if model loaded)│    subject + body → phishing_prob
    └─────────┬───────┘
              │
    ┌─────────▼───────┐
    │ Stacking Layer  │──── Meta-LR on all probabilities
    └─────────┬───────┘
              │
    ┌─────────▼───────┐
    │ Explainability  │──── SHAP feature importance
    │ (if requested)  │──── LIME word contributions
    │                 │──── top_reasons list generation
    └─────────┬───────┘
              │
              ▼
    AnalyzeResponse JSON
```

---

## Phase 6 — Result Display

### Floating Badge (on email open)
```
Content script receives response
    └─ showResult(data) called
         └─ Floating badge injected at bottom-right:
              ┌───────────────────────────────┐
              │ 🚨 TrustMail: PHISHING (78%) ✕│
              └───────────────────────────────┘
```

### Popup Dashboard (on toolbar icon click)
```
chrome.storage checked for trustmail_popup_result
    ├─ Found (from inbox pill click) → display immediately
    └─ Not found → query active tab content script for GET_CURRENT_RESULT
         └─ Renders:
              ├─ Risk ring meter (animated SVG)
              ├─ Risk level + confidence
              ├─ Top 3 reasons
              ├─ Tabs: Overview / Headers / URLs / Explain / History
              └─ Export buttons (JSON / Text)
```

---

## Timing Budget

| Phase | Target | Actual (heuristic mode) | Actual (with models) |
|---|---|---|---|
| Inbox pill appears | < 2s | ~0.3s | ~0.8s |
| Full badge (email open) | < 3s | ~0.5s | ~1.5s |
| Popup render | < 50ms | ~20ms | ~20ms |
| SHAP explanation | < 5s | N/A | ~2s |
