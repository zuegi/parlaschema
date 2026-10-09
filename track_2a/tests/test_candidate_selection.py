import json
from dataclasses import dataclass, field

import pytest

from openparl_extractor.candidate_run import DEVELOPMENT_DOCUMENTS, run_documents, run_field
from openparl_extractor.candidate_selection import (
    CandidateSelection, build_request_body, build_result, local_candidates, parse_selection,
)
from openparl_extractor.candidates import generate_candidates
from openparl_extractor.span_selection import SelectionError
from test_candidates import make_document


@dataclass
class FakeClient:
    content: str = '{"status":"unknown","candidate_ids":[]}'
    finish: str = "stop"
    bodies: list = field(default_factory=list)

    def complete(self, body):
        self.bodies.append(body)
        return {"choices": [{"message": {"content": self.content}, "finish_reason": self.finish}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def inputs():
    document = make_document([[["Betreffend: Wartezeiten bei Gesuchen"],
                              ["von Anna Muster (SP, Zürich)"],
                              ["1. Welche Schritte gibt es?", "a. Schritt eins", "b. Schritt zwei"],
                              ["2. Was kostet es?"]]])
    return document, generate_candidates(document)


def test_fake_client_valid_reconstruction_and_no_raw_document_input():
    document, candidates = inputs()
    client = FakeClient('{"status":"known","candidate_ids":["C1"]}')
    record = run_field(client, "fake", document, candidates, "title", 1)
    assert record["outcome"] == "valid"
    assert record["result"]["values"][0]["text"] == "Wartezeiten bei Gesuchen"
    assert record["request_body"] == client.bodies[0]
    assert record["finish_reason"] == "stop" and record["usage"]["completion_tokens"] == 5
    assert record["payload_hash"]
    assert "Authorization" not in json.dumps(record)


@pytest.mark.parametrize("content", [
    '{"status":"unknown","candidate_ids":["C1"]}',
    '{"status":"known","candidate_ids":[]}',
    '{"status":"partial","candidate_ids":[]}',
    '{"status":"not_found","candidate_ids":[]}',
    '{"status":"known","candidate_ids":[1]}',
    '{"status":"known","candidate_ids":["C1"],"reason":"yes"}',
    '{"status":"known","candidate_ids":["C1"],"kind":"question"}',
    '{"status":"unknown","candidate_ids":[]} extra',
    '{"status":"known","candidate_ids":[',
])
def test_invalid_parser_output_rejected(content):
    with pytest.raises(SelectionError):
        parse_selection(content)


@pytest.mark.parametrize("ids", [["C999"], ["C1", "C1"], ["C1", "C2"], ["C2", "C1"]])
def test_unknown_duplicate_overlapping_and_reverse_submitters(ids):
    document, candidates = inputs()
    with pytest.raises(SelectionError):
        build_result(document, candidates, "submitters", CandidateSelection(status="known", candidate_ids=ids))


def test_question_order_and_parent_subitem_overlap():
    document, candidates = inputs()
    local = local_candidates(candidates, "question_or_request")
    mains = [cid for cid, c in local.items() if c.kind == "main_item"]
    result = build_result(document, candidates, "question_or_request",
                          CandidateSelection(status="known", candidate_ids=mains))
    assert len(result["values"]) == 2
    assert "a. Schritt eins" in result["values"][0]["text"]
    for ids in ([mains[1], mains[0]], ["C1", "C2"]):
        with pytest.raises(SelectionError):
            build_result(document, candidates, "question_or_request",
                         CandidateSelection(status="known", candidate_ids=ids))


def test_duplicate_person_from_different_source_positions_rejected():
    document = make_document([[["von Anna Muster"], ["von Anna Muster"]]])
    candidates = generate_candidates(document)
    ids = [cid for cid, c in local_candidates(candidates, "submitters").items() if c.kind == "name_only"]
    with pytest.raises(SelectionError, match="Duplicate name-only"):
        build_result(document, candidates, "submitters", CandidateSelection(status="known", candidate_ids=ids))


@pytest.mark.parametrize("ids", [[], ["C1"]])
def test_needs_review_allowed_with_supported_portion_or_empty(ids):
    document, candidates = inputs()
    result = build_result(document, candidates, "title",
                          CandidateSelection(status="needs_review", candidate_ids=ids))
    assert result["status"] == "needs_review"


def test_complete_length_whitespace_accepted_and_truncation_not_retried():
    document, candidates = inputs()
    valid = FakeClient('{"status":"known","candidate_ids":["C1"]}' + " " * 50, "length")
    record = run_field(valid, "fake", document, candidates, "title", 1)
    assert record["outcome"] == "valid" and record["finish_reason"] == "length"
    failed = FakeClient('{"status":"known","candidate_ids":[', "length")
    assert run_field(failed, "fake", document, candidates, "title", 1)["outcome"] == "failed"
    assert len(failed.bodies) == 1


def test_closed_schema_and_sampling_limits():
    document, candidates = inputs()
    for name in ("title", "submitters", "question_or_request"):
        body = build_request_body("fake", candidates, name)
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["candidate_ids"]["items"]["enum"] == list(local_candidates(candidates, name))
        assert body["temperature"] == 0 and body["top_p"] == 1
        assert "stop" not in body and "guided_json" not in body
    assert build_request_body("fake", candidates, "question_or_request")["max_tokens"] >= 600


def test_tampered_candidate_text_rejected():
    document, candidates = inputs()
    corrupted = candidates.model_copy(update={"candidates": (
        candidates.candidates[0].model_copy(update={"text": "fabricated"}), *candidates.candidates[1:],
    )})
    with pytest.raises(SelectionError, match="offset reconstruction"):
        build_result(document, corrupted, "title", CandidateSelection(status="known", candidate_ids=["C1"]))


def test_exact_24_calls_two_independent_runs(tmp_path):
    document, _ = inputs()
    docs = [document.model_copy(update={"document_id": did}) for did in DEVELOPMENT_DOCUMENTS]
    client = FakeClient()
    records = run_documents(client, "fake", [(d, generate_candidates(d)) for d in docs], tmp_path / "runs")
    assert len(records) == len(client.bodies) == 24
    assert client.bodies[:12] == client.bodies[12:]
    assert len(list((tmp_path / "runs").glob("*.json"))) == 24
    assert all(r["outcome"] == "valid" for r in records)
    with pytest.raises(FileExistsError):
        run_documents(client, "fake", [(d, generate_candidates(d)) for d in docs], tmp_path / "runs")
    assert len(client.bodies) == 24


def test_scope_guard_before_any_calls(tmp_path):
    document, candidates = inputs()
    client = FakeClient()
    with pytest.raises(ValueError):
        run_documents(client, "fake", [(document, candidates)], tmp_path / "runs")
    assert not client.bodies


def test_network_error_counts_once_and_failed_not_unknown():
    class FailingClient:
        calls = 0

        def complete(self, body):
            self.calls += 1
            raise TimeoutError("timeout")

    document, candidates = inputs()
    client = FailingClient()
    record = run_field(client, "fake", document, candidates, "title", 1)
    assert record["outcome"] == "failed" and record["result"] is None
    assert client.calls == 1
