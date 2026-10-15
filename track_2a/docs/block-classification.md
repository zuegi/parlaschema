# Scoped block classification v0.1 (offline core)

The procedure sheet below is a historical proposal, not the executed
diagnostic matrix or permission for new calls. Historical results and the
current incomplete submission scope are in [the technical report](../technical_report.md).

This is a separate precursor, **not** eight-field domain extraction, document
selection, a PDF/OCR pipeline, document profiles, or a converter. Existing
domain/provenance/reference schemas are unchanged. The checkout had page-tuple
provenance helpers and `check-config`, but no SourceDocument/provider transport.
The new source wrapper reuses `source_pages`; the CLI uses the existing entry
point. These offline modules include no provider implementation, network client,
retry, repair, fallback, second model, or automatic human approval.

## Contract and category-only prompt

`block_classification.py` defines immutable Pydantic inputs and outputs:

- `SourceDocument`: positive document ID, explicit text representation, exact
  page strings. This is supplied text, not proof of PDF/OCR completeness.
- `BlockInput`: unique evaluation block ID, DE/FR/IT language, source and ordered
  candidate ranges, optionally previous/following ranges from the same source.
  Pages are 1-based; offsets are Python Unicode code-point indices, 0-based,
  start-inclusive/end-exclusive, **not** PDF coordinates or UTF-8 byte offsets.
  Each block/context uses at most one contiguous range per page; gaps between
  pages may exclude headers. Ordering, nonoverlap, bounds and nonblank slices
  are checked. Whether the candidate is a complete main question, contains all
  subquestions, or includes every continuation remains the caller/reviewer's
  responsibility; source matching does not establish semantic completeness.
- Prompt payload: language, previous, candidate, following. Every slice remains
  unchanged, including apostrophes, whitespace, soft hyphens and normalization.
  Form feeds between page slices are explicit framing separators, not inferred
  original text. No title/numbering/punctuation heuristic decides the category.
- `ClassificationTransport.complete(request)`: one injected call per candidate.
  Adapters must raise `TransportError` for transport/provider failures.
  Unexpected programming errors propagate; they are not classified as success.
- Parser accepts only one JSON object `{"category":"question"}` (ordinary JSON
  surrounding whitespace allowed), with exactly one category field. Fences,
  commentary, duplicates, extra keys, invalid types/categories and reconstructed
  text/confidence are errors, not repaired.

| Technical value | Meaning |
|---|---|
| `question` | Frage: information sought from addressed body, including subquestions |
| `request` | Forderung: action/measure demanded, possibly phrased as a polite question |
| `answer` | Antwort: executive response; repeated question plus actual answer belongs here |
| `reasoning` | Begründung: motivation/explanation, possibly rhetorical questions |
| `other` | Sonstiges: clearly another function, e.g. signature/procedural metadata |
| `unclear` | Unklar: abstention for ambiguity, insufficient context or unresolved mixed functions |

`unclear` is never a successfully extracted unknown domain field. Category
boundaries above are provisional and must be accepted by human reviewers before
a live comparison; e.g. isolated repeated questions or mixed blocks may abstain.
The fixed system prompt treats all supplied source text as untrusted data.
This instruction is not a proven defense against model prompt injection.

`ClassificationResult` keeps the immutable complete input, including source
ranges/context, and exposes its SHA-256. The input digest covers the whole
validated input, including IDs, language, representation, full source pages,
candidate/context ranges. The separate source-text digest covers the JSON array
of exact page strings. Both use UTF-8 JSON, `ensure_ascii=False`, sorted keys,
compact separators, no Unicode/text normalization. These are representation
fingerprints, **not PDF hashes**, and do not prove provenance outside supplied
text. The source and full input must be retained privately to resolve digests.
Only code attaches identities to category decisions; the model cannot generate
or override references, offsets, original text or domain JSON.

## Reproducible offline replay

From `track_2a/`:

```bash
uv run --frozen pytest -q tests/test_block_classification.py tests/test_block_evaluation.py
uv run --frozen openparl-extractor evaluate-blocks tests/fixtures/block-replay-synthetic.json
```

This command **does not call a model**, read LLM configuration, or open sockets.
It consumes supplied responses through a replay transport. Its JSON dataset has
`version="block-classification-replay-v0.1"`, `label_status="synthetic"` or
`"unreviewed"`, positive `attempts_per_case`, and nonempty `cases`. Each case has
`block`, one `expected` category, and exactly that many `responses`, each either
`{"raw":"...JSON response..."}` or `{"transport_error":"...failure..."}`.
Use the bundled, wholly invented three-language fixture as a format example.
There is no `human_approved` flag or live execution option.

All input blocks and attempts are accounted for. Duplicate block IDs,
missing/extra attempts, invalid ranges or invalid dataset structure reject the
dataset instead of reducing the denominator. CLI exit 0 means valid dataset
processed, **not** correct model output; exit 1 means invalid/unreadable input.
Invalid model output instead remains a `structure_error` attempt in the report.

The fixed denominator is block count times attempts per block, including errors.
One record per block/attempt stores expected/predicted category, input/source
digests, document/representation/ranges/language, outcome and explicit error.
Five mutually exclusive counts are reported: `correct`, `incorrect`,
`abstention`, `structure_error`, `transport_error`. Even expected `unclear`
predicted as `unclear` counts as abstention, not correct; its expected/predicted
agreement is visible separately in the confusion matrix. Non-unclear predictions
against expected `unclear` are incorrect. All six expected-category groups and
all three language groups include denominators, counts and category confusion
matrices, including zero-size groups. Structure/transport errors stay in counts
and denominators, not as fabricated predicted categories.

Tests include invented DE/FR/IT questions, polite action requests, answers with
repeated questions, rhetorical justification, numbered metadata and mixed
blocks; exact Unicode/page continuation, context binding, bad JSON and
transport failure are tested separately. Scripted category agreement proves
**harness behavior only**, not Apertus semantic quality. No aggregate accuracy,
80% claim, live result, human-reviewed reference or end-to-end success follows.
Tiny group counts are diagnostic, not reliable category/language estimates.

Keep real text, labels, replay responses and evaluation output outside checkout,
Docker build context and public fixtures. No rights or publication approval is
implied. Output excludes raw text/responses but still carries references and
transport error details; treat it as private. No private reference is modified.

## Proposed first live decision sheet — NOT approved

This is the original balanced diagnostic proposal, not authorization for the
later unbalanced 18-block exploratory preparation. The
[exploratory runner](exploratory-block-test.md) uses one attempt per input and
separate provisional agent labels. Its live execution remains approval-gated;
there is no network implementation in the offline classifier/replay command.

Before any live call, the coordinator/user must explicitly approve **all**:

1. **Binding baseline:** identify privately stored corpus/version/digest, source
   representation and PDF identities (where applicable), exact block/context
   ranges, language and labels. Name human reviewer and review date per item.
   Review function, complete subquestions/page continuations, contrast cases and
   ambiguous labels; resolve disagreements explicitly. Existing machine drafts
   and synthetic examples are not human-approved gold. No held-out document
   may be used for tuning. Human review does not authorize public redistribution.
2. **Procedure:** freeze input manifest, category policy, exact prompt and parser
   version/hash before calls. Proposed small baseline: **18 distinct blocks,
   one per six-category/three-language cell**, including difficult counterexamples
   and controlled neighbor context. This is a diagnostic set, not a held-out
   evaluation. If extra context conditions are compared, count them as additional
   inputs and reapprove budget before execution. Proposed two independent
   attempts per block; one category-only completion each, sequential, no retries,
   repair, fallback, automatic text correction or omitted failed attempts.
   Confirm actual Apertus model, endpoint, current provider support and settings;
   historical model/endpoint names are not current approval or guided-decoding
   evidence. Proposed temperature 0/top_p 1 only if supported.
3. **Budget cap:** proposed **36 total calls**, including failed calls; no warmup.
   Proposed per-call upper limits: **2,048 input tokens including prompt/context,
   16 output tokens**, totals at most **73,728 input / 576 output tokens**.
   Validate provider tokenizer/output feasibility first, without calls; refuse
   oversized input rather than truncate. Approve a monetary ceiling from current
   provider pricing and credential/account owner; price is presently unspecified.
   Proposed concurrency 1, total wall-clock cap 30 minutes; never relaunch timed
   out attempts. A later live runner must check approvals/caps before network
   contact and record unattempted remainder explicitly on a stop.
4. **Success criterion:** decide before live execution. Proposed strict gate for
   this tiny set: all 36 attempts accounted for; zero structure/transport errors;
   all **30 attempts on 15 determinate blocks** correctly categorized with no
   abstention; all **six attempts on three ambiguous blocks** abstain. Report
   determinate correct/wrong/abstention separately from expected-unclear agreement,
   errors and DE/FR/IT/category diagnostics. This proposal is not a track-wide
   success threshold or proof of generalization. Failure or partial/negative
   feasibility is acceptable; no profiles/full extraction until an explicit
   human decision on adequate local classification.

**Original offline-phase stop.** Baseline identity/human review,
category policy, procedure/provider capabilities, monetary/token/call budget and
success criterion remain open decisions. The classifier/replay command remains
offline; the later exploratory runner has separate explicit permission guards.
