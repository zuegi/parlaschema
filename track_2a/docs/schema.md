# Extraction schema v0.1

One `DocumentExtraction` describes one supplied document, not an entire affair.
`affair_id` groups related documents; it does not authorize merging, deduplication
or looking up unprovided documents. The schema version is required and exactly
`"0.1"`. Selection context (`affair_id`, `document_id`, `parliament`, `language`)
comes from the source registry, not semantic extraction. All eight core keys and
the separate sourced `document_role` are required; extra keys are rejected.
`procedural_events` and affair aggregation are deferred.

## Values and evidence

Every fact keeps `original` in the source language, a nullable typed `normalized`
value, and one or more `sources`. Each source requires a document ID and nonblank
verbatim quote. `page` is the physical 1-based PDF page when actually known,
otherwise null. Every source must refer to the current document. Local item IDs
are structural identifiers, not claims about original numbering.

Normalization never overwrites the original. Null normalization preserves a known
original; it does not make the field unknown. There is no translation or inferred
legal-equivalence operation. Evidence must support the original AND normalization.
The team defines normalization mappings; human review verifies support.

Fields have `status`, `value`, nullable `reason` and optional collection-level
`sources`:

- `known`: nonempty supported value, no reason.
- `unknown`: null value and explicit reason, not an empty string/list. This means
  not established from this document, never globally absent from the affair.
- `partial`: nonempty collection of supported members plus partial-coverage
  reason. Scalar partials are rejected. No invented placeholders.

Reasons: `not_in_document`, `ambiguous`, `unreadable`, `incomplete_source`,
`unenumerated_members`. `not_in_document` cannot describe partial present
collections. Explicit unnamed additional submitters require collection-level
quote evidence and `unenumerated_members`; retain identified people only.
This is a source limitation, distinct from overlooking identifiable submitters
or an unresolved annotation judgment. No known empty collection asserts absence.

Nullable subordinate fields (`kind`, `role`, date `meaning`, optional links/actor)
mean that information is not established. Any present semantic value uses a fact
or evidenced link. Model confidence is omitted; it is not measured accuracy.

## Eight core fields

| Field | Shape and meaning |
| --- | --- |
| `affair_type` | Scalar fact; optional normalized `parliament:local_code`, namespace matching selection context. No cross-canton equivalence implied. `TI:interrogazione` and `TI:interpellanza` remain distinct; translations cannot justify merging. |
| `title` | Scalar fact; do not guess a canonical title from uncertain alternatives. |
| `submitters` | Person/organization records with sourced name and optional sourced kind/role (`submitter`, `co_submitter`, `filing_signatory`). Affiliation is not another submitter; executive document signers are not filing signatories. |
| `addressed_body` | List of sourced body names with optional normalization. Require document support, not institutional convention. |
| `question_or_request` | Ordered top-level blocks with local IDs, sourced text and optional sourced question/request kind. Preserve original numbering/subparts in text; no forced sentence-level or nested decomposition. |
| `executive_answer` | Ordered answer blocks with local IDs and sourced text. Optional evidenced `question_links.target_ids` permit many-to-many alignment; joint answers appear once. Unlinked preamble/general answers remain separate blocks. Repeated questions are not new answer claims. |
| `decision` | Parliamentary decision/outcome blocks with optional sourced actor and evidenced date links. Government adoption of its answer is NOT a parliamentary outcome. If no outcome is observed, unknown. |
| `dates` | Ordered records with local IDs; sourced original date, nullable `{iso, precision}` normalization and optional sourced lifecycle meaning. |

`document_role` is separate context: sourced `filing`, `executive_response`, `other`,
or an unknown field. An executive response to an interpellation remains an
interpellation affair. Role does not become a ninth core field.

Date meanings: `document_date`, `filed`, `executive_response_adopted`,
`parliamentary_decision`. Null means unknown. A header date alone does not prove
filing or adoption. Day/month/year precision requires respectively `YYYY-MM-DD`,
`YYYY-MM`, `YYYY`; invalid dates and mismatched precision are rejected. Never add
a day to month-only text. Keep cover month and explicit adoption day separately.
Dates discussed in policy content are not automatically lifecycle dates.

Answer links reference existing local question IDs; decision links reference
local date IDs. Each collection has unique local IDs and each link unique targets.
Semantic alignment still needs human review even when IDs and quotes are valid.

## Structural validation versus semantic review

`DocumentExtraction.model_validate` checks types, mandatory fields, state
invariants, source-scope IDs, date syntax/precision and local links. Pydantic
validators cannot prove legal equivalence, correct roles, faithful extraction
or parliamentary-versus-executive semantics.

`validate_provenance(extraction, documents)` additionally accepts a caller-supplied
mapping `{document_id: (page1_text, page2_text, ...)}`. It requires document text,
checks page bounds and exact quote occurrence on the specified page, or in
form-feed-joined page text when page is unknown. It does not download, normalize
whitespace, fuzzy-match, or infer pages. Missing/all-blank source text or invalid
quote/page raises an explicit `ProvenanceError`. A cross-page quote must preserve the text
representation's form-feed boundary. API text cannot establish page membership.

Quote occurrence is not semantic entailment. Neither checker establishes PDF
text-layer completeness, OCR fidelity, chart/table accuracy or authoritative
source-version identity. Review the original PDF; record its actual SHA-256 and
declared text representation in a private reference annotation. Do not treat mirror
URL tokens as hashes. Charts that are absent from extracted text remain limitations.

`DocumentResult` separates operational outcomes from semantic unknowns:
`completed` requires extraction/no error; `partial` requires supported extraction
plus error; `failed` requires error/no accepted extraction. Error codes cover
retrieval, parsing, incomplete source, invalid output and provenance. Failed
documents cannot be relabeled as eight successfully unknown fields. Caller must
retain the outcome and make failures visible; unreadable/incomplete-source field
reasons also prevent a completed outcome. These models do not run a pipeline.

## Reproducible export

From `track_2a/`:

```bash
uv run --frozen python -m openparl_extractor.schema_export schemas/__extraction-v0.1.json
uv run --frozen pytest -q
```

Export uses Pydantic v2 `model_json_schema`, fixed sorted UTF-8 JSON and a trailing
newline, with no timestamps or environment values. `uv.lock` pins the generator;
an upgrade requires artifact regeneration/review. Tests compare exported bytes
with the tracked artifact.

The artifact describes `DocumentExtraction`, not execution outcomes or reference
workflow. Cross-field Python validators still run locally; they are not all
expressible in the exported JSON Schema. Full Pydantic gateway acceptance is NOT
established: earlier synthetic probes accepted `json_object` and a tiny strict
`json_schema` only. No gateway calls or adapter are added in this phase.
