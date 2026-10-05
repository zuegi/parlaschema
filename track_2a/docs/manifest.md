# Source manifest

[`data/manifest.json`](../data/manifest.json) is a versioned source index for
16 PDF candidates from 14 cantonal affairs: ZH/de (9), VD/fr (3), TI/it (4).
It is neither a goldset nor Apertus output. Original affair types are preserved;
they describe the affair, not the document role.

Each entry records numeric affair/document IDs, parliament, language, government
level, original type, original `source_url`, OpenParlData mirror `download_url`,
affair document-list `metadata_api_url`, and historical checks.

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

No development/evaluation split is assigned. A later split must group by
`affair_id`, keeping related documents together (notably 336076 and 336073).
The sample covers cantonal sources only; it does not establish multi-level
coverage.

From `track_2a/`, run `uv run --offline pytest` for manifest consistency and
existing configuration tests. Tests read local JSON only; no source checks,
downloads or API calls are performed.
