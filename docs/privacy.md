# TrustMail Privacy Architecture

## Core Principle

> **Your emails never leave your device.**

TrustMail is designed from the ground up to be privacy-preserving. This document explains exactly how data flows through the system and what guarantees are provided.

---

## Data Flow

```
Email opened in browser
        │
        ▼
Content Script (Gmail/Outlook/Yahoo/ProtonMail)
  • Reads email from DOM (client-side only)
  • Strips tracking pixels
  • Extracts: subject, body, URLs, sender
        │
        ▼ (via chrome.runtime.sendMessage — no network)
Background Service Worker (local)
  • Caches results in chrome.storage.session (RAM only)
  • Stores only METADATA in chrome.storage.local (history)
  • NEVER stores raw email body long-term
        │
        ▼ HTTP POST (localhost only)
Local TrustMail Backend (http://127.0.0.1:8000)
  • FastAPI running on YOUR machine
  • All ML inference runs locally
  • No internet connection required for inference
  • Raw email content processed in memory only
  • Audit logs contain ONLY metadata (path, status, latency)
        │
        ▼
ONNX Runtime + Classical ML
  • Models run entirely on your CPU
  • No external API calls
  • No cloud inference
```

---

## What Is Stored

| Data | Where | How Long | Encrypted |
|------|-------|----------|-----------|
| Analysis result | chrome.storage.session | Until browser closes | No (RAM only) |
| Scan metadata (subject, risk, timestamp) | chrome.storage.local | Up to N items (configurable) | No |
| Raw email body | **Never stored** | — | — |
| Settings (backend URL) | chrome.storage.local | Persistent | No |
| Audit logs | Local file (optional) | Configurable | No |

## What Is NEVER Sent

- Email body text
- Email HTML
- Sender email addresses
- Recipient information
- Attachment content
- Any PII from emails

---

## Network Connections

| Connection | When | Purpose |
|---|---|---|
| `localhost:8000` | During scan | Local API only |
| `fonts.googleapis.com` | Extension load | UI fonts (can be removed) |
| None | Inference | ML models are fully local |

**No connections** to:
- OpenAI, Anthropic, Google AI, or any AI provider
- Any analytics service
- Any telemetry endpoint
- Any remote model server

---

## Telemetry

Telemetry is **disabled by default** (`ENABLE_TELEMETRY=false`).

When disabled:
- No usage statistics are collected
- No crash reports are sent
- No model performance data leaves your device

---

## Self-Hosted Remote Backend

Users may optionally configure a remote self-hosted backend URL in extension settings.
In this case, email content IS sent to that URL over HTTPS (if configured with TLS).

**The user must explicitly configure this.** The default is always `localhost`.

---

## Audit Logging

The backend's audit middleware logs:
- Request method and path
- Client IP (local loopback only by default)
- Response status code
- Request duration

It **does NOT log** request or response bodies.

---

## Security Hardening

- Strict Content Security Policy (no inline scripts, no eval)
- HTML sanitization via DOMPurify before any rendering
- Input validation via Pydantic on all API inputs
- Rate limiting on all endpoints
- No eval(), no Function(), no innerHTML without sanitization
