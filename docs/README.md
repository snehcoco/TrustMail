# TrustMail Documentation

> Privacy-first AI email threat detection — 100% local inference.

## Documentation Index

| Document | Description |
|---|---|
| [Architecture](architecture.md) | System overview, data flow, Mermaid diagrams |
| [Machine Learning](ml-documentation.md) | Models, features, training, ONNX, explainability |
| [Email Analysis Workflow](email-analysis-workflow.md) | Full lifecycle from inbox detection to report |
| [Extension Guide](extension-documentation.md) | MV3, service worker, content scripts, popup |
| [Backend Guide](backend-documentation.md) | FastAPI, endpoints, services, model loading |
| [Security](security-documentation.md) | Privacy architecture, CSP, threat model |
| [Developer Guide](developer-guide.md) | Setup, training, adding providers, packaging |
| [API Reference](api-documentation.md) | All endpoints with examples |
| [Performance](performance-documentation.md) | Startup, caching, optimization |

---

## Quick Links

- **Run the backend:** `cd backend && python app.py`
- **Load the extension:** `chrome://extensions/` → Load unpacked → `extension/`
- **API docs:** `http://127.0.0.1:8000/docs`
- **Health check:** `http://127.0.0.1:8000/health`
