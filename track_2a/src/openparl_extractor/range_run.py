import json
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openparl_extractor.range_selection import (
    PROCEDURE_VERSION,
    build_range_result,
    build_request_body,
    parse_range_selection,
)
from openparl_extractor.selection_run import ChatClient, payload_hash
from openparl_extractor.source_document import SourceDocument
from openparl_extractor.span_selection import FIELD_NAMES, FieldName

REQUEST_ERRORS = (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, TypeError, ValueError)


def run_field(
    client: ChatClient, model: str, document: SourceDocument, field: FieldName, clock: Callable[[], float] = time.monotonic
) -> dict[str, Any]:
    body = build_request_body(model, field, document)
    record: dict[str, Any] = {
        "procedure": PROCEDURE_VERSION,
        "document_id": document.document_id,
        "field": field,
        "payload_hash": payload_hash(body),
        "request_body": body,
        "raw_response": None,
        "finish_reason": None,
        "usage": None,
        "seconds": None,
        "outcome": "failed",
        "error": None,
        "result": None,
    }
    started = clock()
    try:
        response = client.complete(body)
        record["raw_response"] = response
        record["usage"] = response.get("usage")
        choice = response["choices"][0]
        record["finish_reason"] = choice.get("finish_reason")
        selection = parse_range_selection(field, choice["message"]["content"])
        record["result"] = build_range_result(document, field, selection).model_dump()
        record["outcome"] = "valid"
    except REQUEST_ERRORS as error:
        record["error"] = f"{type(error).__name__}: {error}"
    record["seconds"] = round(clock() - started, 3)
    return record


def run_documents(client: ChatClient, model: str, documents: list[SourceDocument], out_dir: Path) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for document in documents:
        for field in FIELD_NAMES:
            record = run_field(client, model, document, field)
            name = f"{document.document_id}-{field}.json"
            (out_dir / name).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            records.append(record)
    (out_dir / "overview.md").write_text(render_overview(records), encoding="utf-8")
    return records


def render_overview(records: list[dict[str, Any]]) -> str:
    valid = sum(r["outcome"] == "valid" for r in records)
    lines = [f"# Range selection run ({PROCEDURE_VERSION}): {valid}/{len(records)} technically valid", ""]
    for r in records:
        usage = r["usage"] or {}
        tokens = f"prompt {usage.get('prompt_tokens')}, completion {usage.get('completion_tokens')}"
        lines.append(
            f"## {r['document_id']} / {r['field']} — {r['outcome']} "
            f"(finish_reason={r['finish_reason']}, {r['seconds']}s, {tokens})"
        )
        if r["error"]:
            lines.append(f"error: {r['error']}")
        result = r["result"]
        if result:
            lines.append(f"status: {result['status']}; needs_review: {result['needs_review']}")
            for value in result["values"]:
                prov = value["provenance"]
                lines.append(f"- kind={value['kind']} pages={prov['pages']} spans={prov['span_ids']}")
                lines.append(f"  text: {value['text']}")
        lines.append("")
    return "\n".join(lines)
