# Academia Challenges

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

From the root of the project:

```bash
make run
```

Fill in the [Makefile](Makefile) so that it works on a clean checkout. It is
expected to run the project in a Docker container, since that is how the judges
will run it, without relying on anything already installed on your machine.

Requirements: Docker with Docker Compose and access to the provided Apertus
endpoint. No model weights are required locally.

Create a local `.env` from `.env.example` and set:

```env
LLM_NAME=...
LLM_BASE_URL=...
LLM_API_KEY=...
```

`make run` currently validates the Apertus configuration in Docker.

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

**Licensing requirements**
Please check our Terms & Conditions (6. What you build is open source):
https://hackapertus.ch/terms-and-conditions

## FAQ
💡 https://hackapertus.ch/faq

## Contact
💬 In case you have questions, join the conversation on Discord or send an email to “hello@hackapertus.ch”
