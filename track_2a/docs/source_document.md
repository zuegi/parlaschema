# SourceDocument (Evidence Layer, Phase 1)

Deterministic, model-free representation of a PDF. Code: `source_document.py`, `pdf_extraction.py`.

## Model

`SourceDocument` → `pages[]` → `blocks[]` → `spans[]`

- Document: `document_id`, `affair_id`, `sha256` (of the PDF bytes), `extraction_method`, `warnings[]`.
- Span: `id` (`p003-b012-s004` = page-block-span, 1-based), physical `page`, exact `text`, optional `bbox`, `source` (`native_text`/`ocr`/`api_text`).
- Block = PyMuPDF text block; span = one text line. Pages are never merged before span creation.
- Warnings: `empty_page`, `no_text_layer` (image-only page, OCR needed; OCR is not implemented). Every page has spans or a warning (validated).

## Reconstruction

`reconstruct_text(document, span_ids)` derives original text from an ordered id list. Ids must exist and be in strictly ascending document order. Separators: `\n` within a block, `\n\n` across blocks or pages. Text comes only from spans.

## Decision

Evidence-first: a later model step only selects span ids and closed categories; code copies original text from spans and builds provenance. The model never emits `original` text or quotes; unknown stays unknown.

## CLI

`uv run openparl-extractor extract-source file.pdf --document-id 922604 [--affair-id N] [--out-dir output/source]`

Output goes to `output/` (git-ignored). PDFs are not committed (redistribution rights unclear).

## Phase 2: span-id selection

`span_selection.py`, `selection_run.py`; CLI `select-fields source.json... [--out-dir output/selection]` (needs `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY`; max 12 requests).

One request per field (`title`, `submitters`, `question_or_request`). The model returns only `status` (known/partial/unknown), `reason`, and `blocks[]` of `span_ids` (+ `kind` question/request or null for `question_or_request`). Code validates (ids exist, ascending without overlap, status/id consistency, kind enum, title = one block) and derives text via `reconstruct_text`, whitespace-normalised; the leading question number is removed for `question_or_request`. No retry/repair/fallback; failed requests are `failed`, never `unknown`. Each request logs payload hash, sent body (no key), raw response, usage and duration under `output/`. Technical validity only — correctness is reviewed manually.
