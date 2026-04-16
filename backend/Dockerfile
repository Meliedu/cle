FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Pre-fetch Docling's layout/OCR model weights (~400 MB) so the first PDF
# upload after deploy doesn't block the worker for several minutes while
# HuggingFace is contacted. Safe to fail: the worker falls back to pymupdf.
RUN docling-tools models download || echo "warn: docling model prefetch failed"

COPY . .

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
