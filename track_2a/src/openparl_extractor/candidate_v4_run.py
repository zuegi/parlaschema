import hashlib
import json
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openparl_extractor.candidate_run import DEVELOPMENT_DOCUMENTS, REQUEST_ERRORS
from openparl_extractor.candidate_v3_run import MODEL, render_overview
from openparl_extractor.candidate_v4 import VERSION, build_result, parse_selection, request_body
from openparl_extractor.candidates import CANDIDATE_FIELDS
from openparl_extractor.selection_run import ChatClient, payload_hash
from openparl_extractor.source_document import SourceDocument

OFFLINE_SNAPSHOT = Path("output/analysis/v4_contract_diagnostic/snapshot")
LIVE_SNAPSHOT = Path("output/analysis/candidate_selection_v4_setup")


def _verify(snapshot: Path) -> None:
    for name, sha in json.loads((snapshot / "SHA256SUMS.json").read_text()).items():
        if hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != sha:
            raise ValueError(f"Frozen v4 hash differs: {name}")


def prepare_snapshot(out_dir: Path = LIVE_SNAPSHOT) -> None:
    _verify(OFFLINE_SNAPSHOT)
    out_dir.mkdir(parents=True, exist_ok=False)
    for path in OFFLINE_SNAPSHOT.iterdir():
        if path.name != "SHA256SUMS.json":
            (out_dir / path.name).write_bytes(path.read_bytes())
    for filename in (
        "src/openparl_extractor/candidate_v4_run.py", "src/openparl_extractor/cli.py",
        "src/openparl_extractor/candidate_v3.py", "src/openparl_extractor/candidate_v3_run.py",
        "src/openparl_extractor/selection_run.py", "tests/test_candidate_v4_run.py",
        "docs/source_document.md",
    ):
        path = Path(filename)
        (out_dir / path.name).write_bytes(path.read_bytes())
    _write(out_dir / "SHA256SUMS.json", {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in out_dir.iterdir()
    })


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_snapshot(snapshot: Path = LIVE_SNAPSHOT) -> list[tuple[SourceDocument, dict[str, Any], dict[str, Any]]]:
    _verify(snapshot)
    records = []
    for did in DEVELOPMENT_DOCUMENTS:
        document = SourceDocument.model_validate_json((snapshot / f"{did}.source.json").read_text())
        for field in CANDIDATE_FIELDS:
            data = json.loads((snapshot / f"{did}-{field}.input.json").read_text())
            body = json.loads((snapshot / f"{did}-{field}.body.json").read_text())
            if data["version"] != VERSION or data["document_id"] != did or data["field"] != field:
                raise ValueError("Frozen input scope differs")
            if body != request_body(MODEL, data):
                raise ValueError("Body differs from unchanged offline v4 request")
            records.append((document, data, body))
    return records


def run_field(
    client: ChatClient, document: SourceDocument, data: dict[str, Any], body: dict[str, Any],
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    record = {
        "procedure": VERSION, "document_id": document.document_id, "field": data["field"],
        "request_body": body, "payload_hash": payload_hash(body), "input_hash": payload_hash(data),
        "raw_response": None, "raw_http_error": None, "finish_reason": None, "usage": None,
        "seconds": None, "outcome": "failed", "error": None, "result": None,
    }
    started = clock()
    try:
        response = client.complete(body)
        record["raw_response"] = response
        record["usage"] = response.get("usage")
        choice = response["choices"][0]
        record["finish_reason"] = choice.get("finish_reason")
        record["result"] = build_result(document, data, parse_selection(choice["message"]["content"]))
        record["outcome"] = "valid"
    except urllib.error.HTTPError as error:
        record["error"] = f"HTTPError: HTTP {error.code}"
        record["raw_http_error"] = error.read().decode("utf-8", errors="replace")
    except REQUEST_ERRORS as error:
        record["error"] = f"{type(error).__name__}: {error}"
    record["seconds"] = round(clock() - started, 3)
    return record


def run_requests(
    client: ChatClient, requests: list[tuple[SourceDocument, dict[str, Any], dict[str, Any]]], out_dir: Path,
) -> list[dict[str, Any]]:
    expected = [(did, field) for did in DEVELOPMENT_DOCUMENTS for field in CANDIDATE_FIELDS]
    if [(d.document_id, data["field"]) for d, data, _ in requests] != expected:
        raise ValueError("Exactly one approved twelve-attempt pass required")
    if any(data["version"] != VERSION or body != request_body(MODEL, data) for _, data, body in requests):
        raise ValueError("Requests must use unchanged v4 inputs and bodies")
    out_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for document, data, body in requests:
        record = run_field(client, document, data, body)
        _write(out_dir / f"{document.document_id}-{data['field']}.json", record)
        records.append(record)
        print(f"{document.document_id}/{data['field']}: {record['outcome']}", flush=True)
    overview = render_overview(records).replace("# v3:", "# v4:", 1)
    (out_dir / "overview.md").write_text(overview, encoding="utf-8")
    return records
