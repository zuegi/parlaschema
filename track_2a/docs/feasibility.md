# Schema feasibility: offline assessment v0.1

This is a bounded assessment step, not a converter, new schema, goldset freeze
or extraction experiment. `schema.py`, the exported v0.1 schema and historical
references/results are unchanged. Apertus must still perform semantic extraction
in a later converter; candidate agreement or code-generated parsing cannot
substitute for that requirement.

## Three independent axes

`FieldFeasibility` in `openparl_extractor.feasibility` records one of the existing
eight core fields for one document. The separate document role remains outside
the score. Records bind to the version and SHA-256 of the exact locked
`export_schema()` UTF-8 bytes, checked against the tracked JSON Schema by tests.
Changing the schema requires reassessment, not relabeling old judgments.

- **Source:** `unassessed`, `absent`, `present`, `partial`, `unreadable`,
  `ambiguous`. Reasons reuse the domain schema's vocabulary. References are
  mandatory, including whole-document inspection references for absence.
  Present/partial/ambiguous content also requires document-scoped evidence.
  A parser omission or empty API response never establishes absence.
- **Representation:** `unassessed`, `lossless`, `partial_loss`,
  `not_representable`. Assessed judgments require rationale and existing JSON
  pointers, including `/properties/<field>`. Lossless requires original content
  preserved without an unavailable schema profile. This concerns a specified
  field scope, not whether an entire PDF or parliament fits the schema.
- **Extraction:** `unassessed`, `correct_present`, `justified_unknown`,
  `partial`, `incorrect`, `failed`. Semantic judgment requires prior source and
  representation judgments and an unchanged result reference. An operational
  failure may precede both. Full credit requires technical acceptance, semantic
  correctness/support, completeness, original fidelity, exact evidence and
  correct status/reason. Unreadability, partial source coverage and missed
  available content cannot receive justified-unknown credit.

Use `validate_assessment_sources(record, pages)` to reuse exact quote/page checks.
Occurrence and valid pointers prove neither semantic support nor completeness.
The models validate recorded attestations; they cannot authenticate a reviewer,
verify an externally named file/hash, or prove a human actually reviewed content.

Every new judgment remains `state: draft`. Human review is a separate optional
record with identity, timezone-aware time, verdict and note; agent judgments
cannot become `approved` or gold. Do not invent a review. Old references'
stored review status may be cited as source metadata, never inherited as approval
of a new feasibility judgment.

When a stored reference's quotes do not match the supplied native text
representation, leave source alignment `unassessed`, not `absent` or `unreadable`.
Do not repair quotes, silently fuzzy-match, or blame the schema for differences
between a reference's declared representation and PyMuPDF text.

## Fixed denominator and scope

`summarize_fields(records, frozen_document_ids)` retains eight times the
nonempty, unique document list as denominator. Missing, failed, unsupported and
partial fields are not excluded. Duplicate/out-of-scope records are errors.
Full points require a separate confirming human review. Unresolved coverage
blocks a quality-gate claim. The overall >=80% quality gate remains unchanged;
positive full-credit extraction and justified unknowns are counted separately.
Their extra diagnostic opportunity counts/rates use **draft source judgments**
and are not substitutes for the fixed denominator or measured gold accuracy.
Zero reviewed points on unevaluated drafts is not measured model failure.
Technical availability and zero-unsupported-claims gates still require separate
evaluation; this helper does not claim overall acceptance.

Synthetic tests:

```bash
cd track_2a
uv run --frozen pytest -q tests/test_feasibility.py
```

## Atlas and structure-profile method

Private Dev artifacts retain original labels separately from draft concepts:
parliament names, affair types, actors/roles, statuses, events, date kinds,
document types and links. Each observation needs a source locator, artifact hash,
historical retrieval date (or explicitly unknown), current inspection date and
interpretation status. Missing dimensions remain unknown. Public API field
documentation is an inventory of possible dimensions, not proof that a particular
parliament supplies values; translated/harmonized API labels do not prove legal
or procedural equivalence. Attribution: OpenParlData.ch, metadata CC BY 4.0;
third-party PDF/text redistribution rights require separate authorization.

Structure profiles record observed section order, document role, field regions,
parser limitations and unresolved interpretation. SourceDocument block/span IDs
are private locators, not a new annotation/extraction format. Human-reviewed
references can inform drafts but cannot establish approval of these profiles.
Source hash equality identifies inputs, not parser completeness.

Current scope is four repeatedly used Dev PDFs from three canton affairs,
three languages and two document roles. Two PDFs belong to one affair.
No heldout content is opened for this step. Federal/municipal coverage,
independent multilingual/multi-level gold evaluation, three-type MVP coverage
and cross-parliament utility remain unproven.

Only method and synthetic fixtures are public. Real labels extracted from PDFs,
quotes, profiles, matrices and raw metadata stay in private ignored storage or
session artifacts outside the checkout. No private planning documents are copied
here. Keep sources unchanged; retain reference-version/status conflicts explicitly
until resolved before a binding evaluation.

## Initial domain audit (schema unchanged)

The user-selected next scope is to assess the unchanged document-local
eight-field core first and document additional boundaries. This is not approval
to extend the schema or add profiles. Each private field review must inventory
the required original value, property and relationship, compare native and
reference representations separately, and name a concrete mapping or loss.
Structure/quote validity alone is not semantic completeness.

Source presence can be established from a native passage even when an older
reference's quote does not match that representation. Preserve both rather than
repairing either. Hyphenation, footnote markers, parser control characters,
title boundaries, question grouping and conflicting unknown reasons require
explicit original/policy review when material. Such cells remain `unassessed`;
they are not schema failures or evidence of new extraction performance.
Version private review outputs separately; never overwrite earlier drafts or
inherit their reference's human approval.

The current schema supports original/normalized facts, exact document-scoped
evidence, ordered question/answer blocks, many-to-many local links, decisions
and four named date meanings. Unknown/partial reasons distinguish unnamed
members from unreadable/incomplete sources. These are useful building blocks,
not proof of complete multi-level representability.

Explicit boundaries requiring concrete-case review:

- Actors are modeled as submitters, addressed bodies and optional decision actors;
  no general actor/role registry, affiliation or executive-signatory collection.
- Document-local links cannot represent cross-document answer relations or an
  entire affair's procedural history. `procedural_events` is explicitly deferred.
- Date meaning normalization is limited to four values; unknown normalization
  must not erase an explicitly known procedural meaning.
- Text facts can retain table content as text, but no typed row/column geometry,
  graphics, attachments or attachment links exist. This warrants profile-specific
  review, not automatic rejection of every table, or claiming a parser omission
  is a schema defect. No generic `unmapped_content` expansion is made.

These limits separate broader requirements from the eight-field Dev scope.
A failing extraction of a representable title is an extraction error, not
evidence of schema failure. An unnamed co-submitter or missing chart ordinates
in a text layer is a source limitation, not automatically representation failure.

## Offline startup audit

`make -n -C track_2a run` resolves to `docker compose run --build --rm app`.
There is no root Makefile; the root README correctly changes to `track_2a`,
while the inherited track README's “project root” wording is ambiguous.
Compose requires all three LLM settings even for the default `check-config`.
The Dockerfile installs frozen dependencies and the package, then runs only
configuration validation. It does **not** run PDFtoSchema, produce an extraction,
evaluate quality or demonstrate the requested clean-checkout converter.
No model contact is needed for that entry point.

CI builds the image and checks configuration with dummy settings and network
disabled. This is a startup check, not an end-to-end converter test. The initial
audit does not start services, pull/build images, read `.env`, or use secrets.
Offline config tests can use an explicit synthetic mapping and Compose can be
rendered with an empty environment, disabled env-file loading and dummy values.
The YAML was rendered successfully with standalone `docker-compose` and
`--env-file /dev/null`; `docker compose` was unavailable in the isolated
environment. No Docker build, daemon or end-to-end execution was verified.

The follow-up privacy fix excludes nested/local `output/`, PDFs (including mixed
case extensions), private/raw directories, local env/config, conventional
credential locations, virtualenvs, caches and ignored model weights from the
`track_2a/` build context. Public data/docs/tests/schema are no longer blanket
excluded; the explicit Dockerfile COPY inputs remain unchanged. `.env.example`
is allowed as a public template, not a place for real credentials.

`tests/test_docker_context.py` statically checks these basename-only `**/` rules
using synthetic paths, including nested exclusions and public/startup inclusions.
It deliberately accepts only this narrow pattern subset, not arbitrary Docker
ignore syntax. Compose and CI context/COPY contracts are checked too. No Docker
build or service is needed; these checks do not attest to a daemon's actual
context archive. No dependencies are added.

Keep real sources/references outside the checkout. Pattern exclusions protect
known names/locations, not secrets or private text renamed to an arbitrary
public-looking file, new external contexts, symlinks or future COPY instructions.
Git ignore alone is not a Docker privacy boundary. The unchanged startup still
runs only `check-config`, not a converter.
