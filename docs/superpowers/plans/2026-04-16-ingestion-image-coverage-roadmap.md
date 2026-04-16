# Ingestion image-coverage roadmap

**Status**: Tier 1 landed 2026-04-16. Tiers 2–4 are follow-ups, not scheduled.

## What landed in Tier 1

- **PDF parsing**: Docling primary path with `PictureDescriptionApiOptions` → OpenRouter (Gemini 2.5 Flash). Falls back to pymupdf text-only on failure.
- **PPTX parsing**: duck-typed walk over every shape exposing `.image.blob` (handles `Picture`, `PlaceholderPicture`, and recurses into `GROUP`). SHA-256 dedupe collapses template logos. Concurrency capped at 4 via `asyncio.Semaphore`.
- **VLM client** (`backend/app/services/vlm.py`): non-raising `caption_image`; retries on rate-limit, timeout, connection error, and 5xx; swallows everything else.
- **Inline captions**: `[Figure: …]` inside each page's text so the chunker co-locates the caption with its explanation. `ChunkData.metadata["has_figure"] = True` on chunks containing the marker; threaded through to `Chunk.metadata_` JSON column.
- **Flag**: `ENABLE_FIGURE_CAPTIONS` (default on).
- **Dockerfile**: pre-fetches Docling model weights (~400 MB) so the first upload after deploy isn't stalled.

## Gaps Tier 1 does **not** cover

| Gap | Why it hurts | Tier |
|---|---|---|
| Scanned PDFs (no text layer) | Textbook reading packs return zero chunks. Docling's built-in OCR exists but is slow and inconsistent on messy scans. | 2 |
| Handwritten notes | Student-uploaded notes are unreadable. No OCR today. | 2 |
| Math formulas rendered as images | Equations on a slide become `[Figure: caption]` that paraphrases them — not LaTeX, not searchable by equation text. | 3 |
| Pure figure-only retrieval ("what's in the diagram on slide 12?") | Inline captions are great for grounding, but users asking figure-direct questions still only match via paraphrased caption text. | 3 |
| Tables in PDFs | Docling detects `Table` elements but we only export them flattened into `texts`. Structured table retrieval is possible but unwired. | 3 |
| Caption cache | Re-uploading a revised deck re-bills every identical image. | 2 |
| Formula OCR for scanned math textbook pages | Neither OCR nor VLM produces reliable LaTeX. | 4 |

## Tier 2 — OCR fallback + cost controls

**Trigger**: real uploads are landing with near-empty chunk sets for scanned content.

### Mistral OCR as scanned-PDF fallback
- Route: when `_parse_pdf_pymupdf` returns a ratio of `len(text) / page_count` below a threshold (~200 chars/page), retry the PDF through Mistral OCR (`mistral-ocr-latest`, $2/1k pages).
- New setting: `MISTRAL_API_KEY`, `enable_ocr_fallback`, `ocr_min_chars_per_page`.
- Mistral OCR emits Markdown with figure placeholders — merge its text back into `PageContent` per page, and dispatch any extracted figure images through existing `caption_image`.
- Handwriting: Mistral OCR 3 currently benchmarks best among hosted APIs for handwritten notes (~89%). Cheaper than Azure Doc Intelligence.

### Caption cache
- Key: `sha256(image_bytes)` + `vlm_model`. Store in a new `figure_caption_cache` table:
  `(hash, model, caption, created_at)` with a 30-day TTL.
- Hit path: skip the VLM call in both `_parse_pdf_docling` (needs a Docling `PictureDescriptionLocalClassifier` shim) and `_parse_pptx` (trivial, already keyed by sha256).
- Projected savings: ~40-60% of VLM spend once users re-upload revised decks.

### Observability
- Log line per PDF upload: `(filename, path_used, pages, figures_total, figures_captioned, ocr_used_bool)`.
- Add a cheap `/api/admin/ingestion-stats` endpoint summarizing the last 7 days so we can see when VLM calls are failing silently.

## Tier 3 — Second retrieval index (multimodal)

**Trigger**: figure-direct queries are measurably under-performing in the eval harness.

### Voyage multimodal embeddings
- Embed each extracted figure crop + its caption jointly with `voyage-multimodal-3` (1024d single vector).
- Store in a new `figure_embeddings` table with a parallel pgvector index. Chunks keep the current `text-embedding-3-large` path.
- Query time: dual-retrieve (text chunks + figure embeddings), merge by relevance, dedup.
- Scope: per-course opt-in. Lecture decks that benefit most from figure retrieval are STEM + medical.

### ColPali / ColQwen2.5 page-image index
- Only if Voyage is insufficient. Render each page as an image, ColQwen2.5 emits ~1024 patch embeddings per page, stored in pgvector as multi-vectors using binary quantization + HNSW iterative scan.
- Cost: ~100–300× storage vs Voyage. Use as a *fallback* retrieval path for queries the text index misses.

### Table extraction as its own chunk type
- Docling already detects `Table` elements. Surface them as dedicated chunks with `metadata.content_type = "table"` and serialize as Markdown.
- Enables prompts like "find the table listing reaction rates" to retrieve the actual table, not a paraphrase.

## Tier 4 — Math/formula OCR

**Trigger**: instructors flag that equation-heavy courses lose math at retrieval time.

- **Surya / Texify**: open-source formula recognizer from the Datalab/Marker folks. Runs locally, outputs LaTeX. Hook in only on pages where Docling flags a `Formula` element.
- **Mathpix as premium fallback**: best-in-class accuracy, ~$0.005/page, used only when Surya confidence is low.
- Inline captured formulas as `$$...$$` in the page text so the existing chunker preserves them; they embed alongside surrounding explanation.

## What **not** to do

- Default to a pure page-image retrieval model. Storage blows up, text recall regresses.
- Switch the primary parser to LlamaParse. Hosted, not self-contained, and the quality bar Docling + Gemini clears is already sufficient for the target domain.
- Add more VLM concurrency without measuring. Default `4` is tuned against OpenRouter's Gemini 2.5 Flash rate limits; raise only after confirming the account tier permits it.
- Rely on Nougat for math. Unmaintained since 2024.

## Open questions

- Whether the `chunks.metadata` column should migrate from `JSON` to `JSONB` before adding figure/table filters. `JSONB` indexes are far faster for `metadata->>'has_figure' = true` filters.
- Whether Canvas-pulled PDFs should run a different (cheaper) path — they're often redistributed readings where cost matters more than per-figure fidelity.

## References

- Plan file (Tier 1 execution): `~/.claude/plans/polished-floating-chipmunk.md`
- External: Docling picture annotation docs (docling-project.github.io/docling/examples/pictures_description_api/), Mistral OCR pricing page, Voyage multimodal-3 launch post.
