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
