# Pinned to digest for reproducible builds. Update on dependency review cadence.
FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

WORKDIR /app

# System deps: libgomp1 for Docling's onnxruntime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Pre-fetch Docling model weights (~400 MB) as root, before dropping privileges.
RUN docling-tools models download || echo "warn: docling model prefetch failed"

# Create non-root user and hand over /app + /root/.cache (where docling models land).
RUN addgroup --system app && adduser --system --ingroup app --home /app app \
    && mkdir -p /home/app/.cache \
    && if [ -d /root/.cache ]; then cp -r /root/.cache/. /home/app/.cache/ 2>/dev/null || true; fi \
    && chown -R app:app /app /home/app

COPY --chown=app:app . .

USER app

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
