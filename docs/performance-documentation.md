# TrustMail — Performance Documentation

## Performance Targets

| Operation | Target | Typical (heuristic) | Typical (full AI) |
|---|---|---|---|
| Backend startup | < 10s | ~1s | ~5s |
| Inbox pill appears | < 2s | ~300ms | ~800ms |
| Full email badge | < 3s | ~500ms | ~1.5s |
| SHAP explanation | < 5s | N/A | ~2s |
| Popup render | < 50ms | ~15ms | ~15ms |

---

## Startup Process

```
python app.py
  │
  ├─ 1. uvicorn starts (instant)
  │
  ├─ 2. ASGI lifespan fires
  │    └─ ModelLoader.load_all()
  │         ├─ load_classical()   → unpickle sklearn/xgb/lgb/catboost/lr (~1-3s)
  │         ├─ load_onnx()        → ORT InferenceSession warm-up (~1-2s)
  │         ├─ load_tokenizer()   → load tokenizer.json (~100ms)
  │         └─ load_meta()        → load stacking LR (~50ms)
  │
  └─ 3. Server ready — first request serves immediately (no cold start)
```

### First Request After Startup
All models are pre-loaded in `lifespan`. There is no cold-start latency on the first request — this is by design.

---

## Model Loading Optimization

### ONNX Runtime Session Options
```python
opts = onnxruntime.SessionOptions()
opts.graph_optimization_level = ORT_ENABLE_ALL    # Folds constants, removes dead nodes
opts.intra_op_num_threads = 4                      # Parallel op execution
opts.enable_mem_pattern = True                     # Memory allocation reuse
opts.enable_cpu_mem_arena = True                   # Pre-allocated memory pool
```

**Effect:** Reduces per-inference overhead from ~80ms → ~40ms on typical hardware.

### Classical Model Caching
Pickle files are loaded once into `app.state.model_loader`. Each request calls `predict()` on the already-loaded in-memory models — no disk I/O after startup.

---

## Inbox Scan Performance

### Concurrency Model
```
MAX_CONCURRENT = 8
Queue: unlimited

Drain loop:
  while activeScans < 8 and queue.length > 0:
    pop job → requestIdleCallback → HTTP request
```

**Effect:** At most 8 concurrent HTTP connections to backend. Inbox with 50 emails is scanned in ~7 batches of 8, yielding to browser between each batch.

### requestIdleCallback
```javascript
requestIdleCallback(scan, { timeout: 4000 });
```
- Scan only fires when browser is idle (not in the middle of user interaction)
- Falls back to `setTimeout(scan, 80)` if `requestIdleCallback` not available
- `timeout: 4000` ensures scan eventually fires even if browser stays busy

### WeakMap Deduplication
```javascript
const processed = new WeakMap();
// row element → true
```
- `WeakMap` keys are garbage-collected when the row leaves the DOM
- No memory leak when inbox scrolls and rows are recycled
- O(1) lookup — no performance hit with large inboxes

### MutationObserver Debouncing
```javascript
mo._timer = setTimeout(processVisible, 200);
```
- Batches rapid DOM mutations (e.g. Gmail loading 20 rows at once) into a single scan pass
- 200ms delay is imperceptible to users but prevents 20 redundant calls

---

## Full Scan Performance

### Feature Extraction
| Pipeline step | Approximate time |
|---|---|
| TF-IDF transform (10k features) | 15–40ms |
| Engineered features (URL, headers) | 2–5ms |
| N-gram extraction | 5–15ms |
| **Total feature extraction** | **~20–60ms** |

### Classical Ensemble
Each model runs independently:
| Model | Inference time |
|---|---|
| RandomForest (500 trees) | 3–10ms |
| XGBoost (300 rounds) | 2–8ms |
| LightGBM (300 rounds) | 1–5ms |
| CatBoost (300 rounds) | 2–8ms |
| Logistic Regression | <1ms |
| **Total** | **~10–35ms** |

### ONNX Transformer
| Step | Approximate time |
|---|---|
| Tokenization | 5–15ms |
| ONNX inference (DistilBERT, up to 512 tokens) | 200–600ms |
| Softmax + decode | <1ms |
| **Total** | **~200–600ms** |

### SHAP Explanations
- TreeExplainer on RF+XGB+LGB: ~500ms–2s depending on tree size
- Skipped when `include_explanation=false` (default for inbox scans)

---

## Caching Strategy

### Service Worker Cache (5 minutes)
```javascript
const CACHE_TTL_MS = 5 * 60 * 1000;
const scanCache = new Map();

const cacheKey = btoa(`${email.sender}::${email.subject}`).slice(0, 32);
```

**Cache hit flow:**
```
ANALYZE_INBOX_ROW received
  └─ scanCache.get(key)
       └─ Hit (timestamp < 5min ago)
            └─ Return cached result immediately (0ms backend call)
```

**Impact:** If user views inbox then opens the same email within 5 minutes, the result is served from cache. Zero backend round-trip.

### Cache Cleanup
```javascript
chrome.alarms.create('CLEAN_CACHE', { periodInMinutes: 10 });
// Evicts entries older than CACHE_TTL_MS
```

---

## Optimization Techniques Summary

| Technique | Impact | Where |
|---|---|---|
| Model pre-loading | Eliminates cold start | Backend lifespan |
| ONNX graph optimization | 40% faster inference | `onnx_runner.py` |
| Memory arena | Reduced allocation overhead | ONNX session opts |
| 5-min result cache | Cache hit = 0ms backend | Service worker |
| requestIdleCallback batching | Zero UI jank during inbox scan | `inbox-scanner.js` |
| WeakMap deduplication | No redundant re-scans | `inbox-scanner.js` |
| MutationObserver debouncing | Batches rapid DOM changes | `inbox-scanner.js` |
| Header-only inbox scan | 10x faster than full scan | Service worker |
| Max 8 concurrent | Prevents backend overload | `inbox-scanner.js` |
| GZip responses | Smaller payloads over loopback | Backend middleware |
| `include_explanation=false` | Skips SHAP (saves 500ms–2s) | Inbox scan default |

---

## Profiling

### Backend
```bash
# Install profiling deps
pip install pyinstrument

# Profile a single request
cd backend
python -c "
import asyncio
from api.app import create_app
from api.schemas.request_schemas import AnalyzeRequest
app = create_app()
# ...
"
```

### Extension
1. Open Chrome DevTools on any Gmail page
2. Performance tab → Record → Reload inbox
3. Look for `[TrustMail]` console messages timing
4. Check Network tab for `/api/v1/analyze` request waterfall
