# Exploratory block test preparation (not authorized to run)

This is a tooling/procedure reference, not a claim that no historical calls
took place. Completed diagnostics are summarized in the
[technical report](../technical_report.md); no new or repeated calls are authorized.

This runner is an exploratory comparison against **separate provisional agent
labels**, not human gold, a held-out evaluation, document segmentation or track
acceptance. It is scoped to exactly 18 distinct prepared inputs, **one HTTP
submission attempt each**, no warmups/repeats/retries/repair/fallback. Labels are
7 `question`, 4 `reasoning`, 4 `answer`, 3 `other`; positive `request` and
expected-`unclear` performance cannot be measured. Model `unclear` still means
abstention. Eighteen blocks from four known development PDFs are not eighteen
independent documents. Prior human display-only attestations are neither
inherited nor changed.

## Safe preparation

Use the existing environment configuration (`LLM_NAME`, `LLM_BASE_URL`,
`LLM_API_KEY`); no dotenv/private secret-file discovery. No credentials or request
headers are written. Configuration missing/invalid means dry-run configuration
blocked, not a fabricated current model. `LLM_BASE_URL` is the HTTPS API base,
typically ending in `/v1`; the runner appends `/chat/completions`. Credentials,
query strings and fragments in the URL are rejected. Historical Apertus/CSCS
names do not establish current model/endpoint support. No provider contact is
made to inspect configuration. The stdlib HTTP client does not follow redirects,
use environment proxies, or retry.

All real inputs, separate labels, outputs and approvals must be **outside
checkout/Docker context**. Do not publish private examples. Run from `track_2a/`:

```bash
uv run --frozen openparl-extractor prepare-block-test \
  --manifest /private/path/review-manifest.json \
  --labels /private/path/agent-draft-audit.json \
  --output /private/path/new-dry-run-directory
```

Dry-run is default: no sockets, even with valid model credentials or an approval
file. The output directory must not already exist; no review/result overwrites.
The manifest and separate labels must match their original manifest hash,
exactly 18 unique IDs, every input hash and the scoped category counts. Originals,
human ledger and provisional-label input are never modified. This adapter accepts
the private preparation format, not a new domain/reference schema.

`plan.json` binds source/input, complete category-only system/user messages with
controlled context, exact UTF-8 request bytes, per-input prompt/request hashes,
label/manifest hashes, all package Python code hashes, model/endpoint and limits.
The complete request text is private. No guided decoding or JSON-schema API
support is assumed: the schema contract is expressed in the actual prompt;
there is no hidden omitted schema text or `response_format` claim.
Changing inputs, labels, model, endpoint, settings or package code changes the
approval-bound plan. Source and label snapshots are retained in the private output.

## Proposed limits and explicit approval

Preparation uses 18 calls maximum, sequential; `temperature=0`, `top_p=1`,
`max_tokens=64`, socket timeout 60 seconds, wall-time **scheduling** budget
1,200 seconds. No new call starts with fewer than 60 scheduling seconds left.
Socket timeout is per blocking operation/inactivity, **not a guaranteed hard
overall request or wall deadline**; a slow streaming peer can overrun scheduling
time. Interrupted runs must not be resumed/retried automatically.

Input estimate includes the full system prompt, JSON user text, candidate and
both contexts: **one token per UTF-8 byte plus 512 chat-framing tokens**. It is a
deliberately generous reservation, **not an actual tokenizer count, proven upper
bound, provider usage or guarantee**. No tokenizer dependency is installed.
Reject estimated input above 16,384 tokens; never truncate. Before live execution
the account owner must confirm context/output support and accept/verify token
reservation feasibility. The smallest category-only JSON is roughly two dozen
ASCII bytes; 64 output tokens provide more room than historical 16, but actual
tokenization/provider feasibility is still unverified. A length/refusal/non-stop
finish is a structural error, not repaired or called an abstention.

**Network cannot be authorized by the prepare request alone.** A later user
decision must supply a private approval file with all fields below, actual current
prices and a money ceiling. Missing/unknown prices block the monetary path. Known free
prices may be zero only when explicitly confirmed by the account owner.
No financial safety is claimed from a token estimate or historical configuration.

```json
{
  "version": "exploratory-block-approval-v0.1",
  "plan_sha256": "COPY_FROM_CONFIGURED_DRY_RUN",
  "approved_by": "ACTUAL_APPROVER",
  "approved_at": "ACTUAL_USER_SUPPLIED_APPROVAL_DATE",
  "network_approved": true,
  "private_source_transmission_approved": true,
  "provisional_labels_accepted": true,
  "provider_settings_and_limits_confirmed": true,
  "pricing_confirmed": true,
  "unverified_token_estimate_accepted": true,
  "model": "COPY_FROM_CONFIGURED_DRY_RUN",
  "endpoint": "COPY_FROM_CONFIGURED_DRY_RUN",
  "max_calls": 18,
  "currency": "CONFIRMED_CURRENCY",
  "monetary_limit": "ACTUAL_POSITIVE_LIMIT",
  "input_price_per_million": "ACTUAL_NONNEGATIVE_PRICE",
  "output_price_per_million": "ACTUAL_NONNEGATIVE_PRICE",
  "pricing_source": "ACTUAL_CURRENT_PRICE_SOURCE_AND_DATE"
}
```

This is a template, **not a valid approval**. Proposed conservative cost
reservation uses all 18 input caps, not average text estimates:
`294912 * input_price_per_million / 1000000`
+ `1152 * output_price_per_million / 1000000`, in confirmed currency.
It must fit the supplied ceiling. This assumes approved provider pricing/limits
are honored; unknown usage, tokenization, extra provider fees or incorrect prices
preclude a guaranteed monetary bound. On reported per-call limit breach or
reported cost above ceiling, remaining blocks are recorded `not_sent`. Missing
provider usage leaves actual cost unknown; it is not filled from estimates.

Alternatively, `exploratory-block-quota-approval-v0.1` requires explicit user
confirmation that this exact test is covered by free/prepaid quota, the verbatim
coverage and execution decisions, accepted unverified-provider-support risk,
and the same plan/network/transmission/input/output/call guards. It does not
assert current prices, currency, zero cost or verified provider support.
`approved_at` is null when the decision time was not supplied; actual
`authorization_recorded_at` is separate. Financial reservation/actual cost,
currency and monetary limit remain null in this mode, even with token usage.
Regular price-based approval requirements remain unchanged. Rebinding code for
this budget alternative must preserve original requests/inputs/labels/limits.

Only after separate approval, a later invocation additionally needs
`--approval /private/path/approval.json --allow-network` with a new output
directory. Without **both**, execution stays dry or refuses before network.
Approval binds the current plan/code hash, exact configured model/endpoint,
18-call cap and budget; a preparation lacking configuration cannot be approved.
The runner does not independently verify that an approval file was authored by a
human; it is an explicit local permission artifact, not cryptographic attestation.

## Private operational record and diagnostics

Each input has a durable `prepared` event. Before its sole HTTP attempt a `sent`
event is flushed/fsynced with request hash and `send_attempt=true`; this means
attempted submission, **not proof bytes reached provider**. Each processed input
then has `result`, retaining sanitized raw response body (no HTTP headers),
HTTP status, finish, valid usage, explicit error, latency and category/outcome.
Responses echoing the exact configured credential are redacted. No arbitrary
secret-containing exception messages are retained. Raw private responses may
still include source data. Files are owner-only, directory newly created.

All 18 inputs remain in denominator: `correct`, `incorrect`, `abstention`,
`structure_error`, `transport_error`, or `not_sent` (dry-run/limit-stop).
Reports contain category confusion matrix, category/language diagnostics,
send attempts, latency/wall time, provider-reported usage, missing-usage count,
estimated reservation and price-based actual cost only when usage is complete.
`unclear` never hides a transport or structure failure. No success percentage,
80% acceptance, completeness guarantee or zero-hallucination claim is produced.
CLI exit 0 means a report was written, not model success.

On process interruption or local persistence failure, stop; `prepared`/`sent`
events identify unattempted or indeterminate inputs, and a final report may be
absent. Inspect these privately before any new user-approved experiment; never
rerun automatically or infer a result/abstention. Exactly-once delivery cannot be
proved after a timeout or interruption.

Offline tests use only invented inputs and fake HTTP:

```bash
uv run --frozen pytest -q tests/test_block_live.py tests/test_block_classification.py tests/test_block_evaluation.py
```

**Stop after preparation.** Human approval of exploratory procedure, actual
18-input/labelversion hashes, configuration/provider feasibility, transmission
rights, prices and monetary limit remains required before live execution.
