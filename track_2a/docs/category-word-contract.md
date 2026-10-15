# Explicit category-word-v0.1 opt-in

Preparation descriptions below document the historical method boundaries,
not authorization to repeat completed experiments. See the
[technical report](../technical_report.md) for aggregate results and limitations.

`category-json-v0.1` remains the default. Existing JSON requests, category
definitions, candidate/context semantics and strict parser behavior are preserved.
Frozen runs are not rewritten or rescored. There is no output autodetection,
JSON/word fallback, or repair.

`category-word-v0.1` changes only the output instruction: exactly one of
`question`, `request`, `answer`, `reasoning`, `other`, `unclear`, without a JSON
example. Shared semantic prompt prefix and user payload are unchanged. This
format comparison does not add executive-preamble rules or alter context policy.
The code trims surrounding whitespace and accepts only an exact case-sensitive
vocabulary word. Quotes, fences, JSON, punctuation, explanations, multiple words
and other normalization are rejected. Code returns the typed category and
serializes JSON locally; the model supplies no original text, offsets or JSON.
`unclear` remains abstention.

These unchanged semantic rules belong to the default method `legacy-v0.1`.
Output format and classification method are separate selections.

Explicit configuration is scoped, not a global environment override:
`build_request`, `classify_block`, `parse_category` and live `request_body`
accept the contract argument with JSON default. Replay datasets have an
`output_contract` field (absent means JSON). Live preparation CLI uses
`--output-contract category-word-v0.1`; plan, prompt/request/code hashes, records
and reports bind the selected version. Changing it invalidates prior approval.
LLM connection configuration remains unchanged.

```bash
uv run --frozen pytest -q tests/test_block_classification.py tests/test_block_evaluation.py tests/test_block_live.py
```

Real fixtures stay private. A separate offline-prepared four-input comparison
uses exactly the prior synthetic Q/A/R/O texts, expected labels and HTTP
parameters, changing only the output contract. No live authorization is implied
by implementing or preparing this opt-in. A new user decision must confirm
maximum four sequential calls, one per input, quota coverage and execution;
previous call approvals are exhausted. No reparse of older raw words as results.

## Offline opt-in method source-function-v0.2

`--method source-function-v0.2 --output-contract category-word-v0.1` opts into
new semantic/input rules, **not a new output format**. JSON and legacy word
prompts/defaults remain unchanged. The new method requires the word contract;
unknown methods and incompatible combinations fail explicitly, without fallback.
No global config, provider contact or authorization is implied.

The new prompt distinguishes motivation for an intervention (including motivation
quoted in a response document) from explanatory style alone. Executive answer
bodies and the executive's own preliminary remarks require original source
evidence for the response section. Document role alone is insufficient.
Questions about intended/possible measures remain information questions, not
automatically demands. Clear action demands are requests; metadata/signatures
are other; genuine uncertainty is abstention, not absence.

`BlockInput.assignment` is optional **exact source context for attribution**.
It holds, for example, a manually bounded repeated question heading transferred
out of an answer candidate. New payloads keep `assignment`, `previous`,
`candidate`, `following` distinct. They contain original slices only: no inferred
speaker/role labels, expected categories or approvals. Assignment ranges must
be ordered, in bounds, nonblank and disjoint from every other supplied range.
Existing source/page/offset semantics are unchanged. Empty assignment preserves
legacy input hashes; nonempty assignment participates in the new input hash.
Legacy builders reject nonempty assignment rather than silently discarding it.

There is no automatic boundary detection or header stripping. Callers must
provide verified explicit source ranges and record derivations separately.
Missing/uncertain boundaries must not trigger guessed slicing or claims of
absence. The new method also works with an unchanged candidate and no assignment;
original neighbouring context may supply attribution evidence.

Builder/classifier/live plan helpers accept an explicit `method` argument.
Replay datasets use `classification_method`; absent means `legacy-v0.1`.
Plans, entries, results, reports and request/prompt/code hashes bind the method.
The existing 18-case live approval route is not relaxed for a smaller proposed
comparison. Private derived fixtures and separate bounded authorization are
required before any such run.

```bash
# Existing 18-case private manifest, dry-run only; no network by default.
uv run --frozen openparl-extractor prepare-block-test \
  --manifest /private/source-manifest.json --labels /private/provisional-labels.json \
  --output /private/new-method-preparation \
  --output-contract category-word-v0.1 --method source-function-v0.2
```

A same-derived-payload comparison can pair the original word prompt with the new
prompt using identical candidate/header/context ranges. Such a private diagnostic
control is explicitly **old prompt on new payload**, not an unchanged historical
request or a supported legacy-builder assignment input. It separates prompt
effects conditional on the derived representation; it does not establish the
benefit of transferring headers versus original full blocks. All cases/arms,
errors and abstentions need fixed denominators and prospective labels. No
best-variant selection, retrospective rescoring, gold approval or generalization
from previously seen development documents.
