# Source manifest

[`data/manifest.json`](../data/manifest.json) is a versioned source index for
16 PDF candidates from 14 cantonal affairs: ZH/de (9), VD/fr (3), TI/it (4).
It is neither a goldset nor Apertus output. Original affair types are preserved;
they describe the affair, not the document role.

Each entry records numeric affair/document IDs, parliament, language, government
level, original type, `document_role`, original `source_url`, OpenParlData mirror `download_url`,
affair document-list `metadata_api_url`, and historical checks.

`document_role` records the selection-reference classification from
`machbarkeit/OpenParlData Dokumentauswahl.md` (external to this repository),
not a verified extraction or gold annotation. There are eleven `filing` entries,
three `executive_response` entries (922604, 921072, 541615), and two `unknown`
entries (480176, 540642). The latter selection descriptions do not establish
a filing or response role; the affair type alone cannot establish one.
`unknown` is a flat manifest sentinel, not a `DocumentRole` literal in the
extraction schema. That schema represents unknown roles through field status
`unknown`, null value and an explicit reason. No conversion or role verification
pipeline is implemented.

`verification_basis: historical_reference` means all checks were transcribed
from the selection reference dated 2026-10-05, not rerun for this manifest.
`checked_on` is that historical date, not a freshness guarantee:

- `source_check`: GET with a Range request; only the beginning, up to 1024 bytes,
  was read. HTTP 200 for ZH/TI, 206 for VD; `%PDF-` signature verified.
- `download_check`: mirror fully retrieved, HTTP 200, `%PDF-` signature verified;
  `size_bytes` is the documented mirror size, not the original source size.

No full-content original/mirror comparison was performed. Original responses
reported `application/pdf`, mirrors `application/octet-stream`; Content-Type
alone does not establish the file format. URL path tokens are not verified
content hashes. No hashes, page counts or licenses are asserted.

Global `pdf_redistribution_rights: pending` applies to every document: individual
PDF republication rights remain unchecked. No PDFs or API text are stored here.
`api_text_available: true` records reported API text availability for all entries,
not its completeness or extraction quality. Global
`parser_and_scan_suitability: pending` applies to all entries: PDF parser
compatibility, scan/born-digital status, OCR needs, page counts, text order,
tables and attachments remain unverified. Source checks do not prove successful
extraction.

Manifest version 2 adds `split` to each document without changing frozen selection
metadata or historical checks. Split groups by `affair_id`: development affairs
340291, 336076 and 228191 comprise four PDFs; the other eleven affairs comprise
twelve held-out PDFs. Both documents of 336076 are development; both documents
of 336073 are held out. Do not inspect held-out content for schema or prompt tuning.
The sample covers cantonal sources only; it does not establish multi-level
coverage.

## Local machine inspection on 2026-10-07

[`data/pdf-inspection.json`](../data/pdf-inspection.json) records a separate,
dated inspection of the frozen selection. It does not replace historical
manifest checks or grant parser, annotation or publication approval. The global
pending flags remain unchanged.

All sixteen original PDFs and mirrors were fully retrieved and their actual
SHA-256 values matched pairwise. Poppler 26.06.0 successfully ran `pdfinfo`,
`pdftotext -enc UTF-8` in reading and layout modes, `pdfimages -list`,
`pdfdetach -list` and page rendering. Development was processed first
(four PDFs, thirteen physical pages), followed by heldout (twelve PDFs,
seventy-three pages). Embedded-file counts were zero; this does not exclude
appended pages. All eighty-six pages were viewed as machine layout overviews,
not a full character-level visual transcription or human semantic review.

Document-list API responses use a `data` envelope. Document and affair IDs were
matched before comparing each API text with the complete page-separated Poppler
reading text. Four TI texts agree after stripping whitespace. Twelve other texts
differ; word-token counts are diagnostic only, not accuracy/completeness scores.
Hyphenation, heading spacing, footnotes, page furniture and table order differ.
Even equal text cannot establish graphic completeness or page provenance.

Important source limitations:

- Development document 922604: page 3 table needs row/column reconstruction;
  page 4 vector charts lose plotted yearly values and x-axis labels in PDF/API
  text. API y-axis labels occur after surrounding answer text. The private
  executive-answer draft is partial.
- Heldout 480176: pages 32-34 contain a visible appended draft law but no fonts,
  raster images or extractable text. Heldout 540642: page 19 has the same problem
  for its appended draft decree. These are vector-outline text pages, not evidence
  of raster scans; API text also omits their content.
- Local Apple Vision French OCR was run on those four rendered pages. Results
  are provisional, with line coordinates/confidences retained privately; OCR
  confidence is not verified accuracy. Draft dates use the explicitly declared
  hybrid page representation, not API page guesses.
- Raster charts/diagrams in 480176 and equipment tables/maps in 540642 remain
  incomplete in text. Financial tables and schedules require cell-level visual
  review. No claim that OCR or a text parser fully recovers these structures.

No whole-page raster scans were identified in this machine layout inspection.
That observation is not a blanket no-OCR guarantee. Detailed findings and physical
page references are in the inspection index. Actual PDFs, API responses/text,
hashes, page text, renders, OCR and sixteen reference drafts stay in private
session artifacts outside this repository. See [reference review](goldset.md)
for draft scope and unresolved approvals. No heldout content informed schema or
prompt changes; no schema, prompt, split or goldset was frozen by this review.

From `track_2a/`, run `uv run --offline pytest` for manifest consistency and
existing configuration tests. Tests read local JSON only; no source checks,
downloads or API calls are performed. See [schema](schema.md) for document-scoped
extraction and [reference review](goldset.md) for annotation/publication boundaries.
