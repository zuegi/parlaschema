# Two-task scoped extraction v0.2

This opt-in prototype processes supplied page text in two sequential requests:

1. `metadata`: `affair_type`, `title`, `submitters`, `addressed_body`, `dates`
   and separate `document_role`.
2. `questions`: `question_or_request`, including ordered blocks and subquestions.

Both requests receive the complete, identical page list. The second does not
receive the first model's output. Source IDs, parliament and language come from
the caller and are not model-produced claims. No registry metadata is substituted
for source facts. `executive_answer`, `decision` and all answer/decision links are
unprocessed; no invented unknown values are inserted for them.

This is text-to-scope, not automatic PDF/OCR conversion. Domain/reference models,
their versioned exports and their approvals are unchanged.

## Single-request control (explicit opt-in)

`extract_control` requests the same six core fields and document role in exactly
one HTTP call. `ControlSelection` combines the existing metadata and question
contracts into one closed strict schema; it inherits the question-order validator.
The complete unmodified page list, field rules, resolver, domain types, provenance
checks, task outcomes and scope merge are shared with the two-request variant.
No answers, decisions or links are added.

The control uses 8,192 output tokens by default, versus two requests of 4,096
each; timeout remains 120 seconds per request, temperature 0 and `top_p` 1.
It has no retries, repair calls, fallback or model reviewer. Equal nominal
output budgets do not imply equal input costs or end-to-end time budgets.

An HTTP/timeout/truncation/malformed/non-JSON failure of the shared request fails
both tasks with no extraction. A non-object or unexpected root field also fails
both. Once a valid scoped JSON object is received, metadata and question sections
are validated independently by the same task parsers as before. Missing fields
or invalid spans in one section remain an explicit failed task, preserving a
valid other section as scope `partial`. Source-limit partials follow the existing
contract. Nothing is synthesized for failed or unprocessed fields.

For equivalent synthetic selections, both variants produce the identical
`ScopeResult`; raw diagnostics differ because the control records one response
under `control`, while the default records `metadata` and `questions`.
This equivalence is tested offline, not a claim about model quality.

## Source and transport

Input is `scoped_contract.SourceDocument`:
`{affair_id, document_id, parliament, language, pages}`.
Pages are physical, 1-based when referenced; their strings are the exact declared
representation. The example in `examples/scoped-v02-input.json` is fictional.
`examples/scoped-v02-multisegment-input.json` adds fictional disjoint footnotes
and a question spanning two pages; no real source/reference material is included.
Input hashes, PDF provenance and OCR completeness are caller responsibilities.

The two closed, typed transport schemas are `MetadataSelection` and
`QuestionsSelection`. Each field requires `{status, value, reason, sources}`.
Unknown fields use null value and a reason; known fields require a nonempty
typed value and null reason; partial collections retain their coverage reason.
Optional subordinate categories and date normalization are explicitly null when
not established. No free normalized names, titles or question paraphrases exist.

A text selection is:

```json
{
  "text_spans": [{"page": 1, "start": 7, "end": 20}],
  "sources": [{"page": 1, "start": 0, "end": 20}]
}
```

Offsets count Unicode codepoints in the exact original page string, zero-based,
start inclusive/end exclusive. They are not byte offsets, grapheme positions,
JSON-escape positions or offsets in a numbered prompt wrapper. `page` is 1-based.
The selected text may exclude a name/title label while its supporting source
includes it. The example shape is illustrative, not a span into the fixture.

Text and category evidence are separate. A category selection is
`{value, sources}`, where value has the corresponding v0.2 category type.
Each claim supplies its own source spans; matching spans may be explicitly
supplied for multiple claims, but nothing is inherited automatically.
Type selection adds nullable evidenced `normalized` classification; date
selection adds nullable typed `{iso, precision}`. Date meaning is separate.
No verified type mapping is supplied, so the prompt requires null type
normalization rather than invented equivalence.

## Deterministic resolution and checks

Each span must select a nonblank contiguous substring within its declared page.
For text facts, every selected segment must be fully covered by at least one
declared evidence span on the same page. Coverage cannot be assembled from
multiple incomplete evidence spans. No fuzzy search, text matching, offset
adjustment or repair is performed. Each selected substring is copied exactly,
including whitespace and question numbering; quotes are copied exactly from
their explicitly supplied sources.
No category is inferred from the selected text.

Resolved results validate against scoped field models reusing the existing v0.2
domain types and v0.1 field-state/evidence helpers. Validation includes category
types, ISO precision/calendar validity, claim-specific nonempty evidence,
document scope, exact quote/page checks and local question/date ID uniqueness.
`text_spans` is a nonempty list in physical source order (page, then offset).
Duplicate, overlapping, reversed, blank and out-of-range segments are rejected.
Adjacent segments are allowed. Segments may occupy disjoint parts of one page
(main text plus a footnote, excluding intervening unrelated text) or multiple
pages. `original` joins exact segment substrings with the constant separator
`"\n\n"` between every pair, regardless of page boundary. No trimming or reflow:
existing CRLF, Unicode and boundary whitespace remain; only this documented
whitespace separator is added. One segment produces the identical original as
the previous single-span resolver.

This is an explicit scoped transport change: legacy `text_span` is rejected;
callers must use `text_spans: [old_span]` for single selections. No compatibility
fallback or silent repair is provided. v0.1/v0.2 domain/review models and exports,
ScopeResult, CLI defaults and output diagnostics are unchanged. Saved request
schemas/prompts and comparison manifests from before this change are stale.

Questions are ordered by their first segment, which represents main text.
All selected segments across questions must remain nonoverlapping, but a later
footnote of question 1 may occur after the main text of question 2. The validator
checks overlaps without sorting or repairing the returned questions or their
segments. Separate footnotes do not create an artificial range covering all
intervening questions. Reusing the same selected footnote in multiple questions
is rejected; shared supporting evidence may still be explicitly supplied.

Source-order composition is intentionally not a semantic reading-order engine.
If a footnote precedes its main text, or a shared footnote must become original
text of multiple questions, a separate contract decision is required. No policy
is inferred from model output. Correct footnote association, exclusion of foreign
text, completeness and semantic support are not technically proven by valid spans.
Genuine source limits still require honest partial reporting; page breaks or
disjoint locations alone no longer imply incomplete_source or zero field credit.

Character-offset selection may be difficult for a model, especially for Unicode,
CRLF, long pages and JSON-escaped line breaks. Offline tests establish exact
resolution, not the model's ability to select offsets or complete fields.

## Scoped outcomes and merge

`ScopeResult` uses `scope_version: "0.2"`, caller identity, `state`,
`unprocessed_fields: ["executive_answer", "decision"]`, and named `metadata`/
`questions` task results. There is no `DocumentResult` or full extraction.
The two task-owned sets are disjoint; merge preserves their separately validated
results in fixed task order. Wrong document evidence, duplicate IDs and conflicting
type namespace are rejected again by the scope model.

Each task result has `{state, extraction, error}`:

- `accepted`: scoped extraction and no error.
- `partial`: supported scoped extraction and an explicit source-limit error.
  `unreadable`/`incomplete_source` fields require this state.
- `failed`: explicit error and no accepted extraction.

Overall `accepted` requires both tasks accepted; `partial` retains at least one
usable extraction when either task has failed or reports a source limit;
`failed` retains no extraction. A correct `partial/unenumerated_members` field
remains visible without inventing unnamed people. Blank source text produces two
input failures without a request.

The questions request still executes after a metadata request fails. Failures
are retained, not replaced by successfully unknown fields. There are no retries,
fallback modes, repair calls or model reviewers.

Technical acceptance does not prove category support, recognizable-kind/date-
meaning completeness, correct unknowns, text boundary completeness, correct
addressee, or actual source fidelity. A wrong category with an exact quote can
pass structural checks. Manual reference/evaluation remains necessary; it does
not mean correction of automatic results. No full-document acceptance gate or
internal spike target is claimed by this scoped prototype.

## Transport, CLI and diagnostics

`scoped_llm` uses the existing `LlmConfig` and standard-library HTTP. Authorization
is constructed at request time from the configured `SecretStr`; no request
headers or config secrets are written to diagnostics. Defaults: 4,096 output
tokens per task, 120 seconds per task, temperature 0, `top_p` 1. Each request
uses its own strict JSON Schema. HTTP, timeout, network, malformed, truncated,
empty, non-JSON and schema/span failures produce explicit task errors.
Unsupported strict-schema/parameter errors do not trigger a fallback.

The CLI command is explicit opt-in:

```text
openparl-extractor extract-scope-v02 --input INPUT.json --output RESULT.json
    [--control] [--raw-output PRIVATE-RAW.json] [--max-tokens TOKENS] [--timeout 120]
```

Without `--control`, the existing two-request behavior and 4,096-token per-request
default remain. With `--control`, the default is one request and 8,192 tokens.
An explicitly supplied `--max-tokens` overrides either default.

This command sends page text to the configured endpoint. Only execute with
authorized input and a separately approved model-call budget. Development of
this prototype and its tests makes no actual model calls; publishing a fictional
input is not authorization to run a live experiment. `check-config` remains
unchanged, and no existing default switches to v0.2.

Exit codes: 0 scoped accepted, 1 failed, 3 partial, 2 invalid input/config/options,
4 result/raw output write failure. Source input cannot be overwritten by output;
result and raw paths must differ. Positive finite timeout and positive output
token budget are required. Output paths otherwise overwrite existing files:
use new paths for each controlled run.

Optional raw output is a private JSON envelope:
`{"encoding": "base64", "responses": {"metadata": "...", "questions": "..."}}`.
Each value preserves the exact received HTTP response bytes, including invalid
responses or HTTP error bodies. Absent network/timeout responses are absent
from the envelope, not invented bodies. It contains no recorded request headers;
response content may contain source text or provider-returned sensitive data.
Base64 is not redaction or encryption. Keep the entire envelope private.
Result and raw writes are independently attempted; either failure prevents
successful exit. Validation error diagnostics report paths/types, not entire
model payloads. Endpoint error bodies are not echoed into task errors or logs.
Control raw envelopes use `responses.control` instead of two task response keys.

## Offline tests

From `track_2a/`:

```bash
uv run --frozen pytest -q tests/test_scoped_pipeline.py
```

All HTTP is mocked. Tests cover two requests in fixed order, parameters and
separate schemas, complete multiline questions, independent category evidence,
unknown/ambiguous fields, source partials, Unicode/CRLF, invalid spans/IDs/order,
merge invariants, request/response errors, private raw recording and file failures.
Synthetic expected values have no invented human approval or reference migration.
The full suite also preserves v0.1/v0.2 schema and reference regressions.
Control tests additionally prove exactly one request, combined closed strict
schema, unchanged input, equivalent scoped outcomes, shared invalid/partial
behavior and CLI budget selection, raw recording and file/path protection.
Multi-segment tests cover disjoint footnotes without intervening foreign text,
complete cross-page blocks, independent category evidence, exact Unicode/CRLF
and separator preservation, invalid/duplicate/overlapping/reversed/blank segments,
incomplete evidence coverage, legacy transport rejection, and identical A/B merges.

No live comparison is authorized by adding the control. Reference/input baseline,
evaluation mapping and a frozen request matrix must be decided separately.
The proposed 48-call comparison remains a proposal, not an executed experiment.
