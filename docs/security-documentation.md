# TrustMail — Security Documentation

## Privacy Architecture

TrustMail is designed from the ground up with privacy as a hard requirement, not an afterthought.

```
┌─────────────────────────────────────────────────────────┐
│                  PRIVACY BOUNDARY                        │
│                                                         │
│  Chrome Extension ◄──── 100% local ────► FastAPI       │
│       │                                      │          │
│  No email data                          No network      │
│  sent to cloud                          connections     │
│                                         to internet     │
└─────────────────────────────────────────────────────────┘
```

### What TrustMail collects
| Data | Stored? | Sent Externally? |
|---|---|---|
| Email body content | ❌ Never | ❌ Never |
| Email sender/subject | Memory only during scan | ❌ Never |
| Scan metadata (risk level, timestamp, subject) | ✅ chrome.storage.local | ❌ Never |
| User settings | ✅ chrome.storage.local | ❌ Never |
| Telemetry / analytics | ❌ None collected | ❌ Never |

---

## Offline Inference

All ML inference runs on the user's local machine:

### Extension (Client Side)
- No AI code runs in the extension itself
- Extension only sends structured JSON to `127.0.0.1:8000`
- Connection is loopback only — cannot reach the internet

### Backend (Local Server)
- FastAPI server binds to `127.0.0.1` by default (loopback interface only)
- ONNX Runtime executes the neural network locally on CPU
- Scikit-learn, XGBoost, LightGBM, CatBoost run locally
- No outbound HTTP requests during inference
- Model files are static files on disk (`trained_models/`)

### Network Policy
```python
# config/settings.py
HOST = "127.0.0.1"   # Loopback only — not accessible from LAN

# api/middleware/cors_config.py
ALLOWED_ORIGINS = [
    "chrome-extension://*",
    "http://127.0.0.1:*",
    "http://localhost:*",
]
```

---

## Content Security Policy

### Extension Pages (MV3)
```json
"content_security_policy": {
  "extension_pages": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src http://127.0.0.1:8000 http://localhost:8000; font-src 'self' data:"
}
```

| Directive | Value | Reason |
|---|---|---|
| `default-src` | `'self'` | No external resources |
| `script-src` | `'self'` | No inline scripts, no CDN |
| `style-src` | `'self' 'unsafe-inline'` | Allow `element.style` in content scripts |
| `connect-src` | `127.0.0.1:8000` | Only loopback API calls |
| `img-src` | `'self' data:` | Allow data: URIs for icons |

> [!NOTE]
> No `'unsafe-eval'` or `'unsafe-inline'` for scripts. All JS is in external `.js` files.

### Content Scripts
Content scripts run in the context of the host page and are not subject to the extension's CSP. They do not create `<script>` tags — they only manipulate existing DOM and inject HTML via `innerHTML` (safe, display-only content).

---

## Secure Storage

```javascript
// All storage is chrome.storage.local — NOT sync
// Local = stays on this device only
chrome.storage.local.set({ trustmail_settings: settings });
chrome.storage.local.set({ trustmail_history: history });
```

### What is in history
```json
{
  "id": "...",
  "timestamp": "2024-01-15T10:23:41Z",
  "platform": "gmail",
  "riskLevel": "phishing",
  "riskScore": 0.847,
  "subject": "Urgent: Verify your account",
  "sender": "noreply@paypa1.com"
}
```

**Raw email body is never stored.**

---

## Input Validation

### Extension Side
- All user settings are validated before storage
- Backend URL is stripped of trailing slashes
- No `eval()` or dynamic code execution anywhere in extension

### Backend Side (Pydantic)
```python
class AnalyzeRequest(BaseModel):
    subject: str = Field(max_length=2000)
    body_text: str = Field(max_length=50000)
    body_html: str = Field(default="", max_length=200000)
    sender: str = Field(default="", max_length=500)
    urls: List[str] = Field(default=[], max_items=200)
```

- Max body: 50KB plain text, 200KB HTML
- Max URLs: 200 per email
- Pydantic raises 422 on violation — no 500 leakage

---

## Threat Model

| Threat | Mitigation |
|---|---|
| Man-in-the-middle (API) | Loopback only — no external network path |
| XSS via email content | Content rendered as `textContent` or escaped HTML in popup |
| Malicious model files | Models loaded from local disk only; no remote download |
| Prompt injection via email | ML models don't execute email content as code |
| Extension supply-chain | No external npm packages in production build |
| DOM injection via pill | Pills use `element.style` + controlled `innerHTML` (static emoji+numbers) |

### DOM Injection Safety
The inbox pill `innerHTML` only contains:
- Static Unicode emoji
- A numeric percentage from `Math.round(number * 100)`

Neither is user-controlled — phishing email content cannot influence what appears in the pill.

The tooltip `innerHTML` renders `top_reasons` strings from the backend. These are generated by the ML pipeline (not echoed from raw email content). However, as a defense-in-depth measure, a future version should HTML-encode these strings.

---

## Extension Permissions

| Permission | Why needed |
|---|---|
| `storage` | Save settings and scan history |
| `activeTab` | Read current tab info for badge targeting |
| `scripting` | Programmatic content script injection |
| `alarms` | 10-minute cache cleanup cycle |
| `tabs` | Read tab ID for badge scoping (added in v1.1) |

**Not requested:**
- `<all_urls>` host permission (only mail providers)
- `cookies`
- `history`
- `bookmarks`
- `identity`
