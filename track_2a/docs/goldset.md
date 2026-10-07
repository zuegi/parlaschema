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

### Development-only machine detail pass

On 2026-10-07, all thirteen development pages were additionally inspected
individually using saved local renders, with higher-resolution table/chart
details for 922604. The four private drafts were corrected in place, with
pre-detail backups and private per-document `development-detail-review.json`
notes. Heldout artifact hashes were checked before/after; those files were not
changed. No model endpoint, schema or prompt changes were involved.

- 926587: explicit submitter/document-date context and question kinds strengthened.
  Eight numbered questions remain; unnumbered introductory factor bullets are
  treated as context, a coverage judgment still requiring human review. A
  document date is not silently promoted to a filing date.
- 902686: question 6's quote now excludes the merged page header, not just its
  displayed text. Twelve numbered questions/subparts and submitter attribution
  were checked. Institutional addressee remains ambiguous; another document
  cannot supply missing evidence for this document.
- 922604: table row/column relations were recovered in answer 1 using a visually
  checked, exact Poppler layout excerpt. Its private page-3 evidence representation
  explicitly supplements reading text with that excerpt; it is not an extra PDF
  page. Both charts show nineteen years, 2007-2025, not the requested full range
  from 2005. Captions and the staffing reference were retained; exact annual
  ordinates have no point labels, so interpolation was not asserted as source
  values. The answer collection stays partial. Cross-page answer 7/8's split word
  was rejoined while preserving exact page quotes. Group links use numbered
  headings; role/adoption-date evidence includes the government resolution,
  not a session header alone.
- 541615: links now quote repeated numbered question headings rather than only
  answer prose. Unlinked preamble, answer 2 across pages 2/3, cover-month versus
  adoption-day, and executive signers were checked. Additional consorts remain
  unnamed and the submitter collection remains partial.

All four retain `machine_draft`, `draft`, `review: null`, publication permission
pending and partial operational outcomes. Source-supported corrections and
page/quote validation do not establish full semantic completeness, exact chart
data, human review or publication rights. The inspection index records the
machine detail pass separately from these still-pending boundaries.

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
