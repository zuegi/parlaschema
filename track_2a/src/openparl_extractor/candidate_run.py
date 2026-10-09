import json
import hashlib
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openparl_extractor.candidate_selection import PROCEDURE_VERSION, build_request_body, build_result, parse_selection
from openparl_extractor.candidates import CANDIDATE_FIELDS, CandidateField, CandidateSet, slice_text
from openparl_extractor.selection_run import ChatClient, payload_hash
from openparl_extractor.source_document import SourceDocument

DEVELOPMENT_DOCUMENTS = (541615, 902686, 922604, 926587)
INDEPENDENT_RUNS = 2
FROZEN_INPUTS = Path("output/analysis/candidates_v2_snapshot_final")
REQUEST_ERRORS = (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, TypeError, ValueError)


def load_frozen_inputs(snapshot: Path = FROZEN_INPUTS) -> list[tuple[SourceDocument, CandidateSet]]:
    manifest = json.loads((snapshot / "SHA256SUMS.json").read_text(encoding="utf-8"))
    inputs = []
    for document_id in DEVELOPMENT_DOCUMENTS:
        names = (f"{document_id}.source.json", f"{document_id}.candidates.json")
        for name in names:
            if hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != manifest[name]:
                raise ValueError(f"Frozen input hash differs: {name}")
        document = SourceDocument.model_validate_json((snapshot / names[0]).read_text(encoding="utf-8"))
        candidates = CandidateSet.model_validate_json((snapshot / names[1]).read_text(encoding="utf-8"))
        for candidate in candidates.candidates:
            if slice_text(document, candidate.start, candidate.end) != candidate.text:
                raise ValueError(f"Frozen candidate offsets differ: {candidate.id}")
        inputs.append((document, candidates))
    return inputs


def run_field(
    client: ChatClient, model: str, document: SourceDocument, candidates: CandidateSet,
    field: CandidateField, run: int, clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    body = build_request_body(model, candidates, field)
    record = {
        "procedure": PROCEDURE_VERSION, "run": run, "document_id": document.document_id, "field": field,
        "request_body": body, "payload_hash": payload_hash(body), "raw_response": None,
        "candidate_input_hash": hashlib.sha256(candidates.model_dump_json().encode()).hexdigest(),
        "finish_reason": None, "usage": None, "seconds": None, "outcome": "failed",
        "error": None, "result": None, "raw_http_error": None,
    }
    started = clock()
    try:
        response = client.complete(body)
        record["raw_response"] = response
        record["usage"] = response.get("usage")
        choice = response["choices"][0]
        record["finish_reason"] = choice.get("finish_reason")
        selection = parse_selection(choice["message"]["content"])
        record["result"] = build_result(document, candidates, field, selection)
        record["outcome"] = "valid"
    except urllib.error.HTTPError as error:
        record["error"] = f"HTTPError: HTTP {error.code}"
        record["raw_http_error"] = error.read().decode("utf-8", errors="replace")
    except REQUEST_ERRORS as error:
        record["error"] = f"{type(error).__name__}: {error}"
    record["seconds"] = round(clock() - started, 3)
    return record


def run_documents(
    client: ChatClient, model: str, inputs: list[tuple[SourceDocument, CandidateSet]], out_dir: Path,
) -> list[dict[str, Any]]:
    if tuple(document.document_id for document, _ in inputs) != DEVELOPMENT_DOCUMENTS:
        raise ValueError("Requires exactly the four approved Dev documents in prescribed order")
    if any(c.document_id != d.document_id or c.generator_version != "candidates-v2" for d, c in inputs):
        raise ValueError("Requires matching candidates-v2 inputs")
    out_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for run in range(1, INDEPENDENT_RUNS + 1):
        for document, candidates in inputs:
            for field in CANDIDATE_FIELDS:
                record = run_field(client, model, document, candidates, field, run)
                target = out_dir / f"run{run}-{document.document_id}-{field}.json"
                target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                records.append(record)
                print(f"run{run} {document.document_id}/{field}: {record['outcome']}", flush=True)
    (out_dir / "overview.md").write_text(render_overview(records), encoding="utf-8")
    return records


def render_overview(records: list[dict[str, Any]]) -> str:
    lines = ["# candidates-v2: two independent selections, technical validity only", ""]
    for record in records:
        lines.append(f"## Run {record['run']} / {record['document_id']} / {record['field']}")
        lines.append(
            f"{record['outcome']}; finish_reason={record['finish_reason']}; "
            f"{record['seconds']}s; usage={record['usage']}"
        )
        if record["error"]:
            lines.append(f"Error: {record['error']}")
        if record["result"]:
            lines.append(f"Status: {record['result']['status']}")
            for value in record["result"]["values"]:
                lines.extend([
                    f"- {value['local_id']} / {value['candidate_id']}: {value['candidate_kind']}; "
                    f"role={value['candidate_role']}; provenance={value['provenance']}",
                    "", value["text"], "",
                ])
    lines.extend(["", "## Agreement (not correctness)", ""])
    for first in records[:12]:
        second = next(r for r in records if r["run"] == 2 and r["document_id"] == first["document_id"]
                      and r["field"] == first["field"])
        agreement = (
            first["outcome"] == second["outcome"] == "valid" and first["result"] == second["result"]
        )
        lines.append(f"{first['document_id']}/{first['field']}: {agreement}")
    return "\n".join(lines)
