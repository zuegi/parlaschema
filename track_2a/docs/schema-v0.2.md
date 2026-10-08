# Extraction schema v0.2

Version 0.2 is an explicit, separate domain schema for one supplied document.
Import `openparl_extractor.schema_v02.DocumentExtraction` to use it.
The existing `schema` module, v0.1 export command, CLI and reference annotation
models still use v0.1. No automatic conversion or version selection is provided.

The eight required core fields remain `affair_type`, `title`, `submitters`,
`addressed_body`, `question_or_request`, `executive_answer`, `decision` and
`dates`. `document_role` remains separate, not a ninth core field.
Selection context (`affair_id`, `document_id`, `parliament`, `language`) comes
from the supplied source registry, not a model's interpretation.

## Text versus interpretation

`TextFact` contains only source-language `original` and nonempty `sources`.
It has no free-text normalization. Titles, names, addressed bodies, question
and answer texts, decision texts and actors use this shape.

`Classification[T]` contains a required, nonnull typed `value` and nonempty
`sources`. It has no `original` or `normalized`: a category is an interpretation,
not another quotation. Document role, submitter kind/role, question/request kind
and date meaning use this shape.

Each claim must provide its own evidence explicitly. An item's text evidence
does not automatically become its classification evidence. A passage may support
both claims, but it must be supplied for each claim separately. Field-level
evidence is also distinct and does not replace either claim's sources.

The following example is fictional:

```json
{
  "id": "q1",
  "text": {
    "original": "When will repairs start?",
    "sources": [
      {"document_id": 1, "page": 1, "quote": "1. When will\nrepairs start?"}
    ]
  },
  "kind": {
    "value": "question",
    "sources": [
      {"document_id": 1, "page": 1, "quote": "1. When will\nrepairs start?"}
    ]
  }
}
```

For `original`, only whitespace collapse/trim and removal of the leading question
number and its numbering punctuation from an individual question block are allowed.
Words, order, case, punctuation and numbers within the block must remain unchanged.
This rule does not permit removing numbering from other text fields, translation,
paraphrase, ellipses or automatic hyphenation repair. Quotes must remain exact,
including line breaks and numbering; permitted original formatting never repairs
quotes.

## Field shapes and categories

Every core field and document role uses the existing
`ExtractedField[T]` (`status`, `value`, `reason`, `sources`) state contract.

| Field | Known value |
| --- | --- |
| `document_role` | Classification: `filing`, `executive_response`, `other`. |
| `affair_type` | `AffairType`: text plus optional `normalized` classification containing a namespaced `parliament:local_code`. |
| `title` | Text fact. |
| `submitters` | List of records with text `name`, optional `kind` (`person`, `organization`) and optional `role` (`submitter`, `co_submitter`, `filing_signatory`) classifications. |
| `addressed_body` | List of text facts identifying actually addressed bodies, not merely a letterhead. |
| `question_or_request` | Ordered items with local `id`, text fact `text`, optional `kind` classification (`question`, `request`). |
| `executive_answer` | Ordered items with local `id`, text fact `text`, optional evidenced `question_links`. |
| `decision` | Items with local `id`, text fact `text`, optional text fact `actor` and evidenced `date_links`. Government adoption of its reply is not a parliamentary decision. |
| `dates` | Items with local `id`, `DateFact` in `value`, optional `meaning` classification. |

Affair type normalization is a separate evidenced classification. Its namespace
must match `parliament`; syntax and matching namespace do not establish a correct
local mapping or equivalence between parliaments. Without a verified mapping,
leave `normalized` null and preserve the local type in `original`.

`DateFact` extends text with nullable typed `normalized`:
`{"iso": "2030-05-02", "precision": "day"}`. Day, month and year precision require
`YYYY-MM-DD`, `YYYY-MM` and `YYYY` respectively. The existing calendar validation
is reused; do not invent missing precision. Its sources support the original
date and the normalization. Date meaning has its own explicitly supplied sources,
separate from the date value's sources.

Date meaning categories:

| Value | Meaning |
| --- | --- |
| `document_date` | Date assigned to this document; a bare date label does not establish filing. |
| `filed` | Explicit submission/filing date of the affair. |
| `executive_response_adopted` | Explicit date the executive adopted its response. |
| `parliamentary_decision` | Explicit date of the parliamentary decision. |
| `debated` | Explicit date or period of parliamentary debate/deliberation of this affair, not filing, executive adoption or a decision by implication. |

The date scope includes the document date and explicitly stated procedural dates
of the affair, including debate. Background statistics and generic legal-reference
dates are outside that required scope. Repeated mentions of one date need not
create duplicate items; distinct procedural meanings must not disappear.
The schema does not automatically deduplicate dates or infer their meaning.

Question/request kind and date meaning are required by the extraction contract
when unambiguous in the source. Nullable subordinate classifications preserve
genuine uncertainty; they do not make an omitted recognizable category correct.
Structural validation cannot establish whether the source makes it recognizable.
The same distinction applies to list completeness and justified unknown fields.

## State, identifiers, links and outcomes

The [v0.1 state and link rules](schema.md) are retained:

- `known`: nonempty value, no reason.
- `unknown`: null value and explicit reason.
- `partial`: nonempty collection and partial-coverage reason; no scalar partials
  or invented placeholder values. `unenumerated_members` requires its own
  collection-level evidence.
- Every source refers to the current document. Physical pages are positive
  1-based integers when known, otherwise null.
- Question, answer, decision and date IDs are unique within their collection.
  Answer links target local question IDs; decision links target local date IDs.
  Targets are unique and links have their own nonempty evidence.

`schema_v02.DocumentResult` explicitly accepts v0.2 extraction and retains the
existing outcome invariants. `failed` requires error/no extraction; `completed`
requires extraction/no error; `partial` requires extraction/error. Source reasons
`unreadable` or `incomplete_source` prevent a completed result. Document IDs must
match. An operational error must never become successfully unknown fields.
This is an outcome model, not a new pipeline.

## Provenance and validation limits

`DocumentExtraction.model_validate` enforces shape, categories, state invariants,
scope, date syntax/precision, type namespace and local links.
`openparl_extractor.provenance_v02.validate_provenance(extraction, documents)`
uses the same exact-quote/page checks as v0.1, with an explicitly v0.2-typed entry
point. Text and classification sources are traversed independently; either may
fail without using the other's evidence.

Neither check proves that `original` was faithfully selected or formatted,
that a category is semantically supported, that an answer is complete, that a
link is justified, or that an unknown field is truly absent. Tests explicitly
demonstrate these limits. In particular, an exact quote can accompany an
incorrect interpretation; `completed` is not semantic approval.
No text reconstruction, span resolution, whitespace repair, inferred source
transfer, model verification call or extraction pipeline is introduced here.

## Compatibility and references

v0.2 is not a drop-in shape change to v0.1:

- Text loses free `normalized` strings.
- Categories change from `Fact(original, normalized, sources)` to
  `Classification(value, sources)`.
- Type normalization becomes an optional classification with its own sources.
- Date ISO normalization retains its existing typed structure; date meaning
  becomes a classification, and `debated` is added.

The two modules enforce their own exact `schema_version`. v0.1 bytes, defaults
and approved reference annotations are not modified. No private references are
included or migrated. The original `reference.ReferenceAnnotation` and
`reference.claim_paths` remain v0.1-specific; do not use them to approve v0.2
classifications. The explicit [v0.2 review contract](reference-v0.2.md) provides
separate text, category, normalization and link assessments. Existing approvals
are not automatically transferred; a future migration procedure requires
separate authorization.

## Deterministic export and offline tests

From `track_2a/`:

```bash
uv run --frozen python -m openparl_extractor.schema_export_v02 schemas/extraction-v0.2.json
uv run --frozen pytest -q tests/test_schema_v02.py tests/test_provenance_v02.py tests/test_schema_export_v02.py
```

Export uses locked Pydantic, sorted UTF-8 JSON and a trailing newline, without
timestamps or environment values. Tests compare generated bytes to the v0.2
artifact; existing v0.1 parity/regression tests remain unchanged. The exported
JSON Schema does not encode every Python cross-field validator. Gateway
acceptance and model extraction quality are not established by this work.
