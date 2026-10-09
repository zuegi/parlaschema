import io
import json
import urllib.error

import pytest

from openparl_extractor.candidate_run import DEVELOPMENT_DOCUMENTS
from openparl_extractor.candidate_v4 import build_input as v4_input
from openparl_extractor.candidates import CANDIDATE_FIELDS, generate_candidates
from openparl_extractor.selection_coverage import build_input
from openparl_extractor import selection_coverage_live
from openparl_extractor.selection_coverage_live import load_requests, prepare, request_body, run_field, run_requests
from openparl_extractor.selection_coverage_run import _hash, _write
from openparl_extractor.span_selection import SelectionError
from test_candidate_selection import FakeClient
from test_selection_coverage import fixture


def test_logging_real_body_source_coverage_and_trailing_whitespace():
    document, data = fixture()
    client = FakeClient('{"items":[{"id":"C1","evidence":["E1"],"interpretation":"submitter"}]}' + " \n"*10, "length")
    record = run_field(client, document, data, request_body(data))
    assert record["outcome"] == "valid" and record["finish_reason"] == "length"
    assert client.bodies == [record["request_body"]]
    assert record["usage"] and record["input_hash"] and record["payload_hash"]
    assert record["result"]["coverage"]["semantic_coverage"] == "unverified"
    assert record["result"]["original_values"][0]["text"] == "Anna Muster"
    assert "Authorization" not in json.dumps(record)
    assert not any(k in record["request_body"] for k in ("stop", "guided_json"))


@pytest.mark.parametrize("content", [
    '{"items":[', '{"items":[{"id":"C999","evidence":["E1"]}]}',
    '{"items":[],"status":"known"}',
])
def test_one_attempt_for_invalid_response_no_retry(content):
    document, data = fixture()
    client = FakeClient(content)
    record = run_field(client, document, data, request_body(data))
    assert record["outcome"] == "failed" and record["result"] is None
    assert len(client.bodies) == 1


def test_http_error_raw_no_retry():
    class Client:
        calls = 0

        def complete(self, body):
            self.calls += 1
            raise urllib.error.HTTPError("https://example.test", 503, "unavailable", {},
                                         io.BytesIO(b'{"error":"unavailable"}'))

    document, data = fixture()
    client = Client()
    record = run_field(client, document, data, request_body(data))
    assert client.calls == 1 and record["raw_http_error"] == '{"error":"unavailable"}'
    assert record["error"] == "HTTPError: HTTP 503"


def test_exact_twelve_fake_attempts_persistence_and_no_overwrite(tmp_path):
    document, _ = fixture()
    requests = []
    for did in DEVELOPMENT_DOCUMENTS:
        doc = document.model_copy(update={"document_id": did})
        for field in CANDIDATE_FIELDS:
            data = build_input(doc, v4_input(doc, generate_candidates(doc), field))
            requests.append((doc, data, request_body(data)))
    client = FakeClient('{"items":[]}')
    records = run_requests(client, requests, tmp_path / "run")
    assert len(records) == len(client.bodies) == 12
    assert all(r["result"]["coverage"]["semantic_coverage"] == "unverified" for r in records)
    with pytest.raises(FileExistsError):
        run_requests(client, requests, tmp_path / "run")
    with pytest.raises(SelectionError):
        run_requests(client, requests*2, tmp_path / "extra")
    requests[0][2]["max_tokens"] = 9999
    with pytest.raises(SelectionError):
        run_requests(client, requests, tmp_path / "tamper")
    assert len(client.bodies) == 12


def test_prompt_schema_and_no_global_status_or_redundant_kind():
    _, data = fixture("question_or_request")
    body = request_body(data)
    schema = body["response_format"]["json_schema"]["schema"]
    assert set(schema["properties"]) == {"items"}
    assert schema["$defs"]["Item"]["properties"]["interpretation"]["enum"] == [None]
    assert body["max_tokens"] == 2048 and body["temperature"] == 0 and body["top_p"] == 1


def test_offline_snapshot_inputs_unchanged_and_code_body_hash_guard(tmp_path, monkeypatch):
    offline = tmp_path / "offline"
    source = offline / "snapshot"
    source.mkdir(parents=True)
    document, _ = fixture()
    for did in DEVELOPMENT_DOCUMENTS:
        doc = document.model_copy(update={"document_id": did})
        _write(source / f"{did}.source.json", doc.model_dump(mode="json"))
        for field in CANDIDATE_FIELDS:
            data = build_input(doc, v4_input(doc, generate_candidates(doc), field))
            _write(source / f"{did}-{field}.input.json", data)
    _write(source / "SHA256SUMS.json", {p.name: _hash(p) for p in source.iterdir()})
    _write(offline / "protected_before.json", {})
    monkeypatch.setattr(selection_coverage_live, "OFFLINE", offline)
    snapshot = tmp_path / "freeze"
    prepare(snapshot)
    requests = load_requests(snapshot)
    assert len(requests) == 12
    path = snapshot / "541615-title.body.json"
    path.write_text("{}")
    with pytest.raises(SelectionError, match="freeze"):
        load_requests(snapshot)
