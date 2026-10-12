# Quote-anchor development test

Hypothesis: Apertus can copy question/request starts and ends more reliably than
artificial evidence identifiers. Exact localization does not prove semantics or
completeness. This is a bounded known-gold development experiment, not a rescue
mechanism, production feature or generalization claim.

Only whitespace is collapsed (`\s+` to one ASCII space, outer whitespace trimmed).
Every search character maps to a half-open original SourceDocument-stream range.
Original stream separators match SourceDocument reconstruction; offsets count
Python Unicode characters, not PDF bytes. Returned passages include both anchors;
span-local offsets and pages allow independent original-text verification.
Page labels are metadata. Adjacent page texts join with one search-space, allowing
cross-page anchors without labels. Hyphens, soft hyphens and BEL remain unchanged.
Normalized search text is not the native passage.

Repeated anchors fail, even if a pairing preference could disambiguate them.
Missing, reversed, overlapping or unordered main blocks fail. No nearest-match,
fuzzy matching, truncation, deduplication, candidate hints or second verifier.
Strict JSON is requested in the prompt, not enforced through guided decoding.
Extra text, duplicate keys and non-stop finishes fail; trailing whitespace parses.
Empty blocks do not evidence absence.

Run synthetic tests before `python -m openparl_extractor.quote_anchor_run prepare`.
Provide `--artifacts` outside the checkout and `--source` pointing at the four
authorized SourceDocument files. Preparation freezes code, tests, method, schema,
prompts, four input hashes, exact request bodies and mapping. `live` verifies freeze
and reserves a non-overwritable output directory: exactly one attempt per document,
including HTTP failures; no retry, repair, probe or later tuning.

CSCS `/v1/chat/completions`, `swiss-ai/Apertus-v1.5-70B`, temperature 0, top_p 1,
timeout 120 seconds, max_tokens 2048; no stop/guided_json/response_format parameters.
Only the existing `~/.config/parlaschema/apertus.env` supplies the key, never logged.
Private inputs, raw requests/responses, freeze and assessments stay outside the
checkout and Docker context. No Docker builds or services are needed.

Success requires all four documents' complete main blocks including subquestions,
correct boundaries/order and unique exact localization, without foreign answer
or justification text. One field error fails this bounded hypothesis. Keep native
versus reference transcription conflicts separate; unresolved judgments remain
open. No question-kind obligation or full eight-field/domain score.
