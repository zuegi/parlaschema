# Private references and human review

`ReferenceAnnotation` reuses schema v0.1; it is a reviewable annotation format,
not a verified goldset. No real annotated references or parliamentary excerpts
are published here. Test fixtures are synthetic, including their reviewer names,
dates, document IDs and placeholder hashes; they are not actual human approvals.

## Private machine drafts from the 2026-10-07 inspection

Sixteen real-document candidates were saved outside the repository in the
reviewing session's persistent `files/private_pdf_review/<document_id>/`
artifacts. Each directory has `reference-draft.json`, `document-result.json`
and `annotation-pages.json`, alongside private retrieved source files. This
machine-specific location is not a portable repository dataset. The repository
contains only the metadata/findings index
[`data/pdf-inspection.json`](../data/pdf-inspection.json), not these annotations,
quotes or source content.

Every candidate is `candidate_origin: machine_draft`, `state: draft`,
`publication_permission: pending`, with no human review. All passed
`ReferenceAnnotation` structural validation and `validate_provenance` against
their declared physical-page text. All operational results remain `partial`,
not accepted completed extractions or measured successes. Exact quote occurrence
does not prove interpretation, coverage, correct transcription or legal meaning.

Development candidates cover the eight fields and separate role. Document 922604
has a partial answer collection because chart values remain untranscribed;
541615 has partial submitters because additional consorts are unnamed. Document
902686 retains an ambiguous addressee rather than inferring an institution.
Missing document-scoped answers/decisions are machine judgments requiring review.

Ten shorter heldout candidates have field/role drafts; the two long legislative
documents (480176, 540642) have only partial context/adoption-request drafts.
Their legislative articles, detailed tables and historical interventions/outcomes
remain unannotated. Locally OCR-recovered proposal dates are provisional, without
an inferred adoption meaning. Draft legal wording is not evidence that parliament
already adopted a proposal. Their machine role interpretation `other` does not
overwrite the frozen manifest's selection-reference `unknown`.

Remaining work: verify every field and unknown against original pages, reconstruct
charts/tables and outlined legislative appendices, resolve coverage/transcription
limitations, and conduct explicit human review. No verified goldset, publication
authorization, full-sample accuracy or schema/goldset freeze follows from these
drafts. Heldout annotation was not used to tune schema or prompts.

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
