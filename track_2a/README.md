# Academia Challenges

**ParlaSchema is an incomplete Track 2A submission:** schema/validation
foundation, synthetic offline demo and partial-negative feasibility report.
The requested PDF-to-schema converter is not implemented. See the
[technical report](technical_report.md) for delivered components and limitations.

Submissions must use the Apertus model family.
For Track 2 this means that submitted solutions must be built with Apertus. Other open-weights models can be used to support development, e.g. as automatic judges during evaluation. Their role must be clearly described in the submission report.

💬 In case you have questions, join the conversation on Discord or send an email to “hello@hackapertus.ch”

## How it works
Pick from 5 academia challenges provided by Swiss academic institutions:

- **FHGR:** AI-Powered Job Interview Coach
- **OpenParlData:** Extracting Parliamentary Affairs from PDFs into One Common Structure
- **OST:** Multilingual Natural Language Inference over Swiss Official Voting Booklets
- **UZH:** Detecting Cross-Lingual Semantic Differences in Swiss Government Websites
- **ZHAW:** See It, Say It, Pick It: Vision-Language Grounding for a Real Robot Arm

The challenges incl. submission and judging criteria are described in our **Getting Started guide**:
https://hackapertus.notion.site/getting-started-guide-onlinehack

## Run it

Keep `track_2a/` as it is: don't rename it or move its files, just delete the
other track directories.

From the repository root:

```bash
cd track_2a
make run
```

The [Makefile](Makefile) runs the demo in Docker without local Python or model
weights. A first build may download public base-image/dependency artifacts.

The default `make run` is a key-free synthetic replay demo. Its execution
does not convert PDFs, contact a model or claim extraction quality. Docker with
Docker Compose is required. The optional live/configuration path needs access
to the provided Apertus endpoint; no model weights are required locally.

The default demo runs `evaluate-blocks` on the tracked synthetic fixture.
It prints `mode: offline_replay`, `label_status: synthetic`, a denominator of
3 and counts of 1 correct, 1 abstention and 1 transport error. The error is
scripted fixture data, not a provider failure; the counts are not model accuracy.
Make targets ignore `.env` files. Keep real credentials and private data
outside checkout and Docker context. Export optional LLM settings in your
shell and validate them separately:

```bash
make check-config
```

Missing configuration is reported explicitly by `check-config`; it is not
needed by the offline demo. Only this explicit target forwards `LLM_NAME`,
`LLM_BASE_URL` and `LLM_API_KEY` from the shell; it validates configuration
without contacting the endpoint.

## Local tests

From the repository root, run all tests in your shell:

```bash
cd track_2a
uv run --frozen pytest -q
```

If your shell is already in `track_2a/`, omit `cd track_2a`.
`uv run` prepares the project environment and installs missing dependencies;
`--frozen` uses the existing lockfile without changing it. `-q` reduces test
output. A successful run ends with a summary such as `101 passed`; the count
may change as tests are added. No real API keys or model requests are needed.

To run only the schema export tests, from `track_2a/`:

```bash
uv run --frozen pytest -q tests/test_schema_export.py
```

Alternatively, `make test` runs the full suite from `track_2a/`.

## Offline block classification precursor

The scoped [block classification contract and decision sheet](docs/block-classification.md)
separates source-bound candidate blocks from category-only decisions. It is not
domain extraction or a PDF converter. Run the entirely synthetic offline replay
from `track_2a/`:

```bash
uv run --frozen openparl-extractor evaluate-blocks tests/fixtures/block-replay-synthetic.json
```

No model calls, LLM configuration or live transport are used. Counts include
every attempt, separate abstention/structure/transport errors and diagnostic
category/language groups. Fake responses test the harness, not Apertus quality.
Real baseline human review, procedure, budget and success criterion must be
approved separately before any future live test.

An [exploratory runner](docs/exploratory-block-test.md) can prepare exactly 18
private inputs against separate provisional agent labels. `prepare-block-test`
defaults to no-network dry-run; actual calls require explicit plan-bound
approval, an explicit monetary or confirmed-quota budget and `--allow-network`.
No live experiment or human gold approval is implied by this tooling.

The [versioned category-word opt-in](docs/category-word-contract.md) accepts one
strict vocabulary word and serializes the typed result in code. JSON remains the
default; no autodetection, fallback or retrospective rescoring.

## Current submission scope

This checkout delivers the schema/provenance validation foundation and the
scoped block-classification/replay precursor. It does **not** deliver the
requested PDF-to-schema converter, document segmentation/profiles, a verified
eight-field extraction pipeline, or a verified evaluator. The real Apertus
diagnostics are a small historical feasibility study: 78 calls across distinct
diagnostic series, with provisional labels on four known development PDFs and
no human-approved gold or held-out score. They are reported as separate
aggregates, never as one accuracy figure or a general model claim. The
synthetic replay is reproducible from this checkout; private source documents,
labels, raw responses, approvals and reference drafts are not.

## CI

GitHub Actions runs on pull requests and pushes to `main`, using Python 3.12,
uv 0.8.16 and `uv.lock` (`uv sync --frozen`, `uv run --frozen pytest -q`).
It also builds the Docker image. **Check CLI startup in Docker** runs the explicit
`check-config` command with dummy LLM settings and networking disabled, checking
the entry point, imports and configuration format without calling a model.
CI needs no real API keys and does not deploy or publish images.

## Data
The `data/` directory must not exceed 100 MB.

[`data/manifest.json`](data/manifest.json) version 2 groups development/heldout
assignment by affair: three development affairs/four PDFs, eleven held-out
affairs/twelve PDFs. Held-out content must not inform schema or prompt tuning.
Historical availability checks are not current parser or redistribution approval.
All sixteen entries include a selection-reference `document_role`: eleven filings,
three executive responses and two unknown roles; see [manifest semantics](docs/manifest.md).
[`data/pdf-inspection.json`](data/pdf-inspection.json) records dated local machine
checks of all sixteen PDFs (86 pages). It flags graphic and outlined-text omissions
in PDF/API text, without granting parser or publication approval. Sixteen private
machine drafts remain outside the repository, unapproved and semantically
incomplete; see [review scope](docs/goldset.md).

## Schema and reference review

Schema v0.1 describes one document with eight required core fields, separate
document role, source-backed originals/normalizations and explicit
known/partial/unknown states. See [field semantics](docs/schema.md) and
[private reference review](docs/goldset.md). Affair merging, real verified
gold annotations, extraction pipeline and evaluator are not implemented.

Regenerate the versioned JSON Schema from locked Pydantic:

```bash
uv run --frozen python -m openparl_extractor.schema_export schemas/extraction-v0.1.json
```

Tests check export parity, structural provenance, review invariants and split
consistency using synthetic data. Full exported-schema gateway acceptance is
unproven. Keep actual PDFs/text/quotes/references outside this repository pending
rights review; human reference approval does not authorize publication.

## 📦 Submission Requirements & Deliverables
❗️ Submissions are not handled on Devpost. Submit through our website only:
http://hackapertus.ch/online-hack/submissions

Requirements differ by challenge. See the description of the challenge you are entering for the exact deliverables.


## ⚖️ Judging Criteria
Judging criteria also differ by challenge. See the respective challenge description.


## Support

Code: Apache-2.0. Documentation: CC BY 4.0. OpenParlData source metadata:
CC BY 4.0. These licenses do not authorize third-party PDF/text redistribution
or model transmission; private references and source rights remain separate.

**Licensing requirements**
Please check our Terms & Conditions (6. What you build is open source):
https://hackapertus.ch/terms-and-conditions

## FAQ
💡 https://hackapertus.ch/faq

## Contact
💬 In case you have questions, join the conversation on Discord or send an email to “hello@hackapertus.ch”
