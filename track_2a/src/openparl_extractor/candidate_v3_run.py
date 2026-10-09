import hashlib
import json
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openparl_extractor.candidate_run import DEVELOPMENT_DOCUMENTS, REQUEST_ERRORS, load_frozen_inputs
from openparl_extractor.candidate_v3 import VERSION, build_input, build_result, parse_selection, request_body
from openparl_extractor.candidates import CANDIDATE_FIELDS
from openparl_extractor.selection_run import ChatClient, payload_hash
from openparl_extractor.source_document import SourceDocument

MODEL = "swiss-ai/Apertus-v1.5-70B"
SNAPSHOT = Path("output/analysis/candidate_selection_v3_setup")


def prepare_snapshot(out_dir: Path = SNAPSHOT) -> None:
    documents = load_frozen_inputs()
    out_dir.mkdir(parents=True, exist_ok=False)
    files = [
        Path("src/openparl_extractor/candidate_v3.py"), Path("src/openparl_extractor/candidate_v3_run.py"),
        Path("src/openparl_extractor/cli.py"), Path("tests/test_candidate_v3.py"),
        Path("docs/source_document.md"),
    ]
    for path in files:
        (out_dir / path.name).write_bytes(path.read_bytes())
    for document, candidates in documents:
        (out_dir / f"{document.document_id}.source.json").write_text(document.model_dump_json(indent=2))
        for field in CANDIDATE_FIELDS:
            data = build_input(document, candidates, field)
            _write(out_dir / f"{document.document_id}-{field}.input.json", data)
            _write(out_dir / f"{document.document_id}-{field}.body.json", request_body(MODEL, data))
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in out_dir.iterdir()}
    _write(out_dir / "SHA256SUMS.json", hashes)


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_snapshot(snapshot: Path = SNAPSHOT) -> list[tuple[SourceDocument, dict[str, Any], dict[str, Any]]]:
    hashes = json.loads((snapshot / "SHA256SUMS.json").read_text())
    for name, sha in hashes.items():
        if hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != sha:
            raise ValueError(f"Frozen v3 hash differs: {name}")
    requests = []
    for did in DEVELOPMENT_DOCUMENTS:
        document = SourceDocument.model_validate_json((snapshot / f"{did}.source.json").read_text())
        for field in CANDIDATE_FIELDS:
            data = json.loads((snapshot / f"{did}-{field}.input.json").read_text())
            body = json.loads((snapshot / f"{did}-{field}.body.json").read_text())
            if data["document_id"] != did or data["field"] != field or data["version"] != VERSION:
                raise ValueError("Frozen v3 input scope differs")
            if body != request_body(MODEL, data):
                raise ValueError("Frozen body differs from current v3 procedure")
            requests.append((document, data, body))
    return requests


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
        raise ValueError("Exactly one approved four-document/three-field pass required")
    out_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for document, data, body in requests:
        record = run_field(client, document, data, body)
        _write(out_dir / f"{document.document_id}-{data['field']}.json", record)
        records.append(record)
        print(f"{document.document_id}/{data['field']}: {record['outcome']}", flush=True)
    (out_dir / "overview.md").write_text(render_overview(records), encoding="utf-8")
    return records


def render_overview(records: list[dict[str, Any]]) -> str:
    lines = ["# v3: one pass, technical validity only", ""]
    for record in records:
        lines.extend([
            f"## {record['document_id']}/{record['field']}",
            f"{record['outcome']}; finish={record['finish_reason']}; {record['seconds']}s; usage={record['usage']}",
        ])
        if record["error"]:
            lines.append(f"Error: {record['error']}")
        if record["result"]:
            result = record["result"]
            lines.append(f"Status={result['status']}; reason={result['reason']}")
            lines.append(f"Status evidence: {json.dumps(result['status_evidence'], ensure_ascii=False)}")
            for value in result["values"]:
                lines.extend([
                    f"### {value['id']} / category={value['category']}", value["text"], "",
                    f"Provenance: {json.dumps(value['provenance'], ensure_ascii=False)}",
                    f"Evidence: {json.dumps(value['evidence'], ensure_ascii=False)}", "",
                ])
    return "\n".join(lines)
