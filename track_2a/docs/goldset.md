# Private references and human review

`ReferenceAnnotation` reuses schema v0.1; it is a reviewable annotation format,
not a verified goldset. No real annotated references or parliamentary excerpts
are published here. Test fixtures are synthetic, including their reviewer names,
dates, document IDs and placeholder hashes; they are not actual human approvals.

## Split and scope

Manifest v2 fixes development affairs 340291, 336076, 228191 (four PDFs) and
eleven held-out affairs (twelve PDFs). All related documents stay in the same
split. Do not open held-out content for schema/prompt tuning. Each reference
describes one document; affair aggregation and merging are deferred.

## Annotation lifecycle

Keep real PDF/text/quotes/reference files outside the repository until publication
rights are reviewed and explicitly authorized. Metadata attribution is
**Source: OpenParlData.ch** under CC BY 4.0; this does not establish third-party
PDF/text/quote redistribution rights. Do not send parliamentary source documents
to a model service without separate authorization.

Private annotation includes:

- `reference_version: "0.1"`, candidate origin (`machine_draft` or `human_authored`),
  state (`draft`, `in_review`, `approved`, `rejected`) and full extraction.
- Original PDF SHA-256, declared text representation and source limitations.
  Compute hash from actual retrieved bytes, never infer it from a mirror URL.
- Separate `publication_permission`: `pending`, `authorized` or `denied`.
  Accuracy approval never changes this automatically.
- When reviewed, reviewer identity/kind, timezone-aware timestamp and assessments
  of all eight fields, document role and each semantic fact/link path.

A machine candidate starts as draft. Candidate origin stays machine-origin after
human correction/review; it does not mean approved. Approval requires
`reviewer_kind: human`, identity/timestamp, exact review coverage and resolved
judgments. This validates explicit recorded attestations, not authentication or
proof that a person actually performed review. Draft/in-review may retain
unresolved judgments. Rejection requires a review.

For present fields/facts/links, approved assessments require `accuracy: correct`,
`support: supported`, `unknown: null`. For unknown fields, require
`accuracy: correct`, `support: null`, `unknown: justified`. Review notes are optional.
Assessments may record incorrect/unsupported/unresolved/unjustified judgments
before correction, but cannot approve those references.

`claim_paths(extraction)` enumerates every sourced fact/link using positional
JSON-pointer-style paths, e.g. `/submitters/value/0/name` or
`/executive_answer/value/1/question_links`. Review both original and normalized
content in each fact. Editing/reordering items requires corresponding review
updates; do not reuse stale positional assessments. Collection-level support,
coverage and unnamed-member evidence are assessed in the field judgment.
Correctly represented source limitations can be approved, unlike unresolved
annotation omissions. No unnamed person is invented.

Review against the original PDF: verify title/type, submitter versus executive
signer, directly addressed body, all question/subquestion blocks, grouped answers,
parliamentary outcome versus executive answer adoption, date meaning/precision,
quotes/pages, normalization and omissions. Text existence checks cannot do this.
Run `validate_provenance` against declared private page text separately.
`ReferenceAnnotation` validates recorded review structure; it does not implicitly
fetch sources, authenticate reviewer identity or run a source registry check.

## Evaluation contract, not an implemented evaluator

Eight document-scoped fields over sixteen selected documents give 128 intended
field outcomes (development 32, heldout 96), reported separately. Do not claim a
full-sample metric using only an approved subset; report annotation coverage.
No measured accuracy or verified goldset exists yet.

The >=80% correct-and-supported or correctly-unknown gate is internal, not an
official challenge score. Supported partial collections remain visible and get
no full-field success credit, even when a human approved their faithful
representation of explicit source limitations. Separately report present-field
extraction, justified unknowns, partial collections, unsupported/hallucinated
items and document failures. Review collections at item level to avoid hiding
mistakes under one field score. Failed documents contribute unsuccessful outcomes,
never silent denominator exclusions or correctly-unknown credit.

Reference approval, extraction outcome, internal scoring and publication
authorization are distinct. No evaluator or automatic semantic judge is included.
