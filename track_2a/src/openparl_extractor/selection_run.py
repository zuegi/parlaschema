import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from openparl_extractor.config import LlmConfig
from openparl_extractor.source_document import SourceDocument
from openparl_extractor.span_selection import (
    FIELD_NAMES,
    FieldName,
    build_field_result,
    build_request_body,
    parse_selection,
)

REQUEST_TIMEOUT_SECONDS = 120
MAX_LIVE_REQUESTS = 12


class ChatClient(Protocol):
    def complete(self, body: dict[str, Any]) -> dict[str, Any]: ...


class HttpChatClient:
    def __init__(self, config: LlmConfig):
        self._url = str(config.base_url).rstrip("/") + "/chat/completions"
        self._key = config.api_key.get_secret_value()

    def complete(self, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"},
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.load(response)


def payload_hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def run_field(
    client: ChatClient, model: str, document: SourceDocument, field: FieldName, clock: Callable[[], float] = time.monotonic
) -> dict[str, Any]:
    body = build_request_body(model, field, document)
    record: dict[str, Any] = {
        "document_id": document.document_id,
        "field": field,
        "payload_hash": payload_hash(body),
        "request_body": body,
        "raw_response": None,
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
        selection = parse_selection(field, response["choices"][0]["message"]["content"])
        record["result"] = build_field_result(document, field, selection).model_dump()
        record["outcome"] = "valid"
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, TypeError, ValueError) as error:
        record["error"] = f"{type(error).__name__}: {error}"
    record["seconds"] = round(clock() - started, 3)
    return record


def run_documents(client: ChatClient, model: str, documents: list[SourceDocument], out_dir: Path) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
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
    lines = [f"# Selection run: {valid}/{len(records)} technically valid", ""]
    for r in records:
        usage = r["usage"] or {}
        lines.append(f"## {r['document_id']} / {r['field']} — {r['outcome']} ({r['seconds']}s, tokens {usage})")
        if r["error"]:
            lines.append(f"error: {r['error']}")
        result = r["result"]
        if result:
            lines.append(f"status: {result['status']} — reason: {result['reason']}")
            for value in result["values"]:
                prov = value["provenance"]
                lines.append(f"- kind={value['kind']} pages={prov['pages']} spans={prov['span_ids']}")
                lines.append(f"  text: {value['text']}")
        lines.append("")
    return "\n".join(lines)
