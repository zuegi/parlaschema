# Reference review contract v0.2

Import `openparl_extractor.reference_v02.ReferenceAnnotation` explicitly for
v0.2 references. The v0.1 `reference` module and its claim paths remain unchanged.
This contract does not migrate references, assign reviewers or perform a review.

## Reference and review shapes

`ReferenceAnnotation` retains the existing workflow keys:

- `reference_version`: required literal `"0.2"`.
- `candidate_origin`: `machine_draft` or `human_authored`.
- `state`: `draft`, `in_review`, `approved` or `rejected`.
- `extraction`: explicitly v0.2 `DocumentExtraction`.
- `source`: existing PDF SHA-256, declared text representation and limitations.
- `publication_permission`: `pending`, `authorized` or `denied`.
- `review`: nullable v0.2 `HumanReview`.

`HumanReview` reuses the existing assessment and identity requirements and adds
required `review_version: "0.2"` without a default. Reviewer name, human/machine
kind and timezone-aware review timestamp must be supplied explicitly.
`fields` covers exactly the eight core fields; `document_role` has its own
assessment; `items` maps exact claim paths to separate assessments.

Each assessment contains `accuracy`, `support`, `unknown` and optional `note`.
An approved present claim requires `correct`, `supported` and null `unknown`.
An approved unknown field requires `correct`, null `support` and `justified`.
These are explicit attestations, not computed semantic conclusions.

## Deterministic claim paths

`reference_v02.claim_paths(extraction)` traverses model fields in declaration
order and collections by index. Paths begin with `/`; indexes are zero-based.
They identify the actual reviewed extraction, not stable identifiers across
reordering or migration.

Each present text fact, classification, date normalization and link is a claim:

| Claim | Example path |
| --- | --- |
| Original question text | `/question_or_request/value/0/text` |
| Question classification and its own evidence | `/question_or_request/value/0/kind` |
| Local affair-type original | `/affair_type/value` |
| Optional normalized type classification | `/affair_type/value/normalized` |
| Original date text and its sources | `/dates/value/0/value` |
| Optional ISO date and declared precision | `/dates/value/0/value/normalized` |
| Optional date-meaning classification | `/dates/value/0/meaning` |
| Explicit answer/question relation | `/executive_answer/value/0/question_links` |
| Explicit decision/date relation | `/decision/value/0/date_links` |

Unlike v0.1's terminal `Fact` traversal, v0.2 continues into a text fact's
optional classification or date normalization. Neither can escape review
because the enclosing text has been assessed. Date ISO value and precision
form one typed normalization claim; its assessment must cover both.
Null optional values generate no claim path. Present optional values always do.
Field-level partial-coverage evidence is assessed with its field; it is not
silently inherited by nested text or classification claims.

## Approval invariants

`approved` requires an explicit v0.2 human review, all eight field assessments,
the separate document-role assessment, and exactly the full claim-path set.
Missing, wrong, stale or extra claim paths are rejected. Each present claim
must independently pass its assessment invariants; a supported text does not
attest its category or its link. Correctly assessed source-limited `partial`
references remain possible, without claiming complete extraction.

`draft` and `in_review` permit `review: null`; `approved` does not.
`rejected` requires a review. In-progress reviews may contain unresolved
assessments but cannot approve. A machine review cannot authorize approval.

Each text/category/link retains its own mandatory extraction evidence.
Reference validation does not run quote matching: separately call
`provenance_v02.validate_provenance` with the declared pages. Human assessments
cannot replace missing sources, and a declared supported assessment does not
prove that its quote occurs. Neither validator verifies reviewer identity,
whether a human actually performed the review, or semantic truth. Accurate
human attestation and source verification remain caller responsibilities.
Approval is never publication permission.

## Future migration rule

Any future converted v0.1 reference must initially use `state: "in_review"` and
`review: null`. The old reference and human approval remain unmodified provenance
in the separately retained original; they are not v0.2 approval.
Do not copy reviewer identity, timestamp or old positive assessments into a new
approval. Do not infer any reviewer identity or review time.

After conversion, source verification and a new explicit human review must
attest the actual v0.2 text, category, normalization and link paths. Only then
may the caller request `approved`. Merely relabelling the reference version is
rejected by version/shape checks; copying a v0.1 review is additionally rejected
by required `review_version` and exact claim-path coverage.
The schema cannot determine whether a caller fabricated a newly labelled
attestation, so this rule is not an automated proof of fresh human activity.

No migration function, private reference changes or automatic approval transfer
is implemented. A future migration procedure and the choice of input/reference
baseline require separate authorization.

## Offline verification

From `track_2a/`:

```bash
uv run --frozen pytest -q tests/test_reference_v02.py tests/test_reference.py
```

Tests use fictional documents and explicitly synthetic reviewer identities/times.
They cover complete approval, all present optional claims, missing/wrong paths,
independent text/category judgments and sources, date precision, links,
unreviewed migration state and rejected v0.1 approval reuse.
No PDF, private gold annotation or model call is required.
