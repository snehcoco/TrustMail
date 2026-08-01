# TrustMail — Extension Documentation

## Manifest V3 Structure

```json
{
  "manifest_version": 3,
  "name": "TrustMail — AI Email Threat Detector",
  "version": "1.1.0",

  "background": { "service_worker": "background/service-worker.js", "type": "module" },

  "content_scripts": [
    { "matches": ["https://mail.google.com/*"],
      "js": ["content/inbox-scanner.js", "content/gmail.js"] }
  ],

  "permissions": ["storage", "activeTab", "scripting", "alarms", "tabs"],

  "content_security_policy": {
    "extension_pages": "default-src 'self'; script-src 'self'; ..."
  }
}
```

### Why `type: "module"` on service worker?
Allows ES module imports in the service worker. Required for the TypeScript source build (Vite produces ESM output).

---

## Background Service Worker

**File:** `extension/background/service-worker.js`

### State
| Variable | Type | Purpose |
|---|---|---|
| `scanCache` | `Map<string, {result, timestamp}>` | 5-min result cache keyed by `sender::subject` |
| `CACHE_TTL_MS` | `number` | Cache time-to-live (300,000ms) |

### Message Handlers

| Message Type | Direction | Purpose |
|---|---|---|
| `ANALYZE_EMAIL` | Content → SW | Full email analysis (body + headers) |
| `ANALYZE_INBOX_ROW` | Content → SW | Lightweight inbox scan (header-only) |
| `SET_POPUP_RESULT` | Content → SW | Store pre-loaded result for popup |
| `CHECK_BACKEND` | Popup → SW | Health-check backend API |
| `GET_SETTINGS` | Popup → SW | Read user settings |
| `GET_SCAN_HISTORY` | Popup → SW | Return past scan records |
| `CLEAR_HISTORY` | Popup → SW | Delete scan history |
| `GET_CURRENT_RESULT` | Popup → Content | Get last result from open email |

### Cache Key Strategy
```javascript
const cacheKey = btoa(`${email.sender}::${email.subject}`).slice(0, 32);
```
Same key for inbox scan and full scan — opening an email after inbox scan reuses the cached result.

### Alarm: Cache Cleanup
```javascript
chrome.alarms.create('CLEAN_CACHE', { periodInMinutes: 10 });
```
Evicts entries older than 5 minutes every 10 minutes.

---

## Inbox Scanner Engine

**File:** `extension/content/inbox-scanner.js`

### API
```javascript
window.__tmScanner.observe({
  rowSelector: 'tr.zA',           // CSS selector for inbox rows
  extractFn:   myExtractFunction, // (row: Element) => ScanData
});
```

### `ScanData` Shape
```javascript
{
  subject:    string,   // Email subject
  sender:     string,   // Sender email address
  urls:       string[], // URLs found in the row (if any)
  platform:   string,   // 'gmail' | 'outlook' | 'yahoo' | 'protonmail'
  emailId:    string,   // Stable ID for caching
  subjectEl:  Element,  // Where the pill gets appended
}
```

### Concurrency Model
```
Queue (unlimited)
    └─ Drain loop: pop job while activeScans < MAX_CONCURRENT (8)
         └─ requestIdleCallback → chrome.runtime.sendMessage
              └─ Callback: activeScans--, drain()
```

### Pill States
1. **Loading** — animated spinner while backend responds
2. **Result** — colored emoji pill (`🟢 12%` | `🟡 28%` | etc.)
3. **Error** — grey `—` pill when backend is offline

---

## Content Scripts

### Provider-Specific Selectors

| Provider | Row Selector | Subject Selector | Sender Selector |
|---|---|---|---|
| Gmail | `tr.zA` | `.bog`, `.y6` | `.zF` (email attr) |
| Outlook | `div[role="option"]`, `div[data-convid]` | `[class*="subject"]` | `[class*="sender"]` |
| Yahoo | `li[data-test-id]`, `li[data-item-id]` | `[data-test-id*="subject"]` | `[data-test-id*="from"]` |
| ProtonMail | `div[data-element-id]`, `li.item-container` | `[class*="subject"]` | `[class*="sender"]` |

### Email Open Detection

| Provider | Trigger Selector |
|---|---|
| Gmail | `[data-message-id]` attribute on email container |
| Outlook | `h1` inside `.allowTextSelection` |
| Yahoo | `h1[data-test-id="message-subject"]` |
| ProtonMail | `h1[data-testid="message:subject"]` |

### Script Load Order (per provider)
```
document_idle fires
    1. inbox-scanner.js loads → sets window.__tmScanner
    2. gmail.js loads → sets window.__trustmailGmailLoaded guard
         ├─ Sets up MutationObserver for email open detection
         └─ Calls activateGmailInboxScanner() → waits for __tmScanner
```

---

## Popup (`popup/index.html` + `popup/popup.js`)

### DOM Structure
```html
<div class="header">   <!-- TrustMail logo + backend status pill -->
<div id="app">         <!-- Dynamic content rendered by popup.js -->
```

### Startup Logic
```javascript
DOMContentLoaded:
  1. checkBackend() — health-check API, update status pill
  2. chrome.storage.get('trustmail_popup_result')
       ├─ Found → renderResult(storedResult), clear storage
       └─ Not found → render() → query active tab content script
```

### Tab Panels
| Tab | Content |
|---|---|
| Overview | Suspicious keywords, AI model predictions, threat categories |
| Headers | SPF/DKIM/DMARC results with color indicators |
| URLs | Risk-sorted URL list with threat tags |
| Explain | Top reasons + SHAP feature importance bars |
| History | Last 20 scans with subject, sender, risk, date |

### Export Functions
- `exportJSON()` — full `AnalyzeResponse` as JSON download
- `exportText()` — human-readable security report as `.txt`

---

## Options Page (`options/index.html` + `options/options.js`)

### Settings Storage
```javascript
chrome.storage.local.set({ trustmail_settings: { ... } });
```

### Configurable Settings
| Setting | Default | Description |
|---|---|---|
| `backendUrl` | `http://127.0.0.1:8000` | Backend API base URL |
| `autoScan` | `true` | Auto-scan emails on open |
| `includeExplanations` | `true` | Include SHAP/LIME in responses |
| `notifyOnPhishing` | `true` | Show badge alert on phishing |
| `maxHistoryItems` | `100` | History retention limit |

---

## State Management

TrustMail uses **chrome.storage.local** as its persistence layer. No IndexedDB, no cookies.

| Key | Type | Purpose |
|---|---|---|
| `trustmail_settings` | Object | User preferences |
| `trustmail_history` | Array | Past scan records (last 100) |
| `trustmail_popup_result` | Object | Pre-loaded result from inbox pill click |

### Content Script Local State
Each content script maintains ephemeral in-memory state:
- `currentEmailId` — prevents duplicate full scans
- `lastResult` — returned to popup via `GET_CURRENT_RESULT`
- `badge` — reference to floating badge DOM element

### Inbox Scanner State
- `processed` (WeakMap) — tracks scanned rows without memory leaks
- `queue` / `activeScans` — concurrency control
- `tooltip` — singleton tooltip DOM element
