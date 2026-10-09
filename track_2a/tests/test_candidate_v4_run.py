import io
import json
import urllib.error

import pytest

from openparl_extractor.candidate_run import DEVELOPMENT_DOCUMENTS
from openparl_extractor.candidate_v4 import build_input, request_body
from openparl_extractor.candidate_v4_run import MODEL, run_field, run_requests
from openparl_extractor.candidates import generate_candidates
from test_candidate_selection import FakeClient
from test_candidate_v4 import inputs, selection


def test_valid_logging_and_complete_length_response():
    document, data = inputs()
    client = FakeClient(selection().model_dump_json() + " \n " * 10, "length")
    body = request_body(MODEL, data)
    record = run_field(client, document, data, body)
    assert record["outcome"] == "valid" and record["finish_reason"] == "length"
    assert record["request_body"] == body == client.bodies[0]
    assert record["usage"] and record["payload_hash"] and record["input_hash"]
    assert "Authorization" not in json.dumps(record)
    assert record["result"]["values"][0]["text"] == "Anna Muster"


@pytest.mark.parametrize("content", [
    '{"status":"known","items":[',
    '{"status":"known","reason":null,"status_evidence":[],"items":[{"id":"C999","category":"submitter","evidence":["E1"]}]}',
])
def test_failures_count_once_no_repair(content):
    document, data = inputs()
    client = FakeClient(content)
    result = run_field(client, document, data, request_body(MODEL, data))
    assert result["outcome"] == "failed" and result["result"] is None
    assert len(client.bodies) == 1


def test_http_failure_preserved_no_retry():
    class Client:
        calls = 0

        def complete(self, body):
            self.calls += 1
            raise urllib.error.HTTPError("https://example.test", 503, "unavailable", {}, io.BytesIO(b'{"error":"unavailable"}'))

    document, data = inputs()
    client = Client()
    record = run_field(client, document, data, request_body(MODEL, data))
    assert record["outcome"] == "failed" and record["raw_http_error"] == '{"error":"unavailable"}'
    assert client.calls == 1 and record["error"] == "HTTPError: HTTP 503"


def test_exact_twelve_fake_calls_scope_and_no_overwrite(tmp_path):
    requests = []
    document, _ = inputs()
    for did in DEVELOPMENT_DOCUMENTS:
        doc = document.model_copy(update={"document_id": did})
        for field in ("title", "submitters", "question_or_request"):
            data = build_input(doc, generate_candidates(doc), field)
            requests.append((doc, data, request_body(MODEL, data)))
    client = FakeClient('{"status":"not_found","reason":"not_found","status_evidence":[],"items":[]}')
    records = run_requests(client, requests, tmp_path / "run")
    assert len(client.bodies) == len(records) == 12
    assert len(list((tmp_path / "run").glob("*.json"))) == 12
    with pytest.raises(FileExistsError):
        run_requests(client, requests, tmp_path / "run")
    with pytest.raises(ValueError):
        run_requests(client, requests * 2, tmp_path / "extra")
    assert len(client.bodies) == 12
