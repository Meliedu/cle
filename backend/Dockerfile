# Pinned to digest for reproducible builds. Update on dependency review cadence.
FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

WORKDIR /app

# System deps:
#   libgomp1                   — Docling's onnxruntime
#   libgl1 libglib2.0-0 libxcb1 libsm6 libxext6 libxrender1
#                              — OpenCV (cv2) runtime, pulled in transitively by
#                                docling_ibm_models/tableformer. Without these,
#                                docling's PDF pipeline raises ImportError on
#                                first use and we fall back to pymupdf (losing
#                                figure captions).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Pre-fetch Docling model weights (~400 MB) as root, before dropping privileges.
RUN docling-tools models download || echo "warn: docling model prefetch failed"

# Create non-root user with /home/app as HOME (docling's model cache lives at
# $HOME/.cache). Keep /app as WORKDIR for the code checkout.
RUN addgroup --system app && adduser --system --ingroup app --home /home/app app \
    && mkdir -p /home/app/.cache \
    && if [ -d /root/.cache ]; then cp -r /root/.cache/. /home/app/.cache/ 2>/dev/null || true; fi \
    && chown -R app:app /app /home/app

COPY --chown=app:app . .

# Docker's USER directive does not auto-populate HOME from /etc/passwd; set it
# explicitly so libraries that read $HOME/.cache (docling, huggingface) find
# the prefetched model weights.
ENV HOME=/home/app
USER app

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
