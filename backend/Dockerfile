# TrustMail Backend — Dockerfile
# ================================
# Multi-stage build:
#   Stage 1 (builder): Install Python deps + ONNX runtime
#   Stage 2 (runtime): Minimal image with only what's needed for inference
#
# Build:  docker build -t trustmail-backend .
# Run:    docker run -p 8000:8000 -v ./trained_models:/app/trained_models trustmail-backend

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 trustmail && \
    chown -R trustmail:trustmail /app
USER trustmail

# Create model directory (mount volume here in production)
RUN mkdir -p trained_models logs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Port
EXPOSE 8000

# Environment overrides for production container
ENV HOST=0.0.0.0 \
    PORT=8000 \
    RELOAD=false \
    WORKERS=2 \
    LOG_LEVEL=INFO

# Entry point
CMD ["python", "app.py"]
