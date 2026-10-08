import json

import pymupdf
import pytest

from openparl_extractor.pdf_extraction import extract_source_document
from openparl_extractor.selection_run import payload_hash, run_documents, run_field
from openparl_extractor.span_selection import (
    SelectionError,
    build_field_result,
    build_request_body,
    parse_selection,
)


@pytest.fixture
def document(tmp_path):
    pdf = pymupdf.open()
    page = pdf.new_page()
    for y, text in [(72, "Interpellazione"), (132, "1. Perché il Governo"), (150, "tace?"), (210, "2. Quando?")]:
        page.insert_text((72, y), text)
    page = pdf.new_page()
    page.insert_text((72, 72), "Risposta")
    path = tmp_path / "d.pdf"
    pdf.save(path)
    return extract_source_document(path, 1)


class FakeClient:
    def __init__(self, content=None, error=None):
        self.content, self.error, self.bodies = content, error, []

    def complete(self, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        return {"choices": [{"message": {"content": json.dumps(self.content)}}], "usage": {"total_tokens": 5}}


def ids(document):
    return list(document.spans_by_id())


def sel(status, blocks, reason="r"):
    return json.dumps({"status": status, "reason": reason, "blocks": blocks})


def test_valid_selection_and_question_number_removed(document):
    a, b, c, d, _ = ids(document)
    blocks = [{"span_ids": [b, c], "kind": "question"}, {"span_ids": [d], "kind": None}]
    result = build_field_result(document, "question_or_request", parse_selection("question_or_request", sel("known", blocks)))
    assert [v.text for v in result.values] == ["Perché il Governo tace?", "Quando?"]
    assert result.values[0].provenance.span_ids == [b, c]
    assert result.values[0].provenance.pages == [1]
    assert result.values[1].kind is None


def test_multi_page_provenance(document):
    all_ids = ids(document)
    s = parse_selection("title", sel("known", [{"span_ids": [all_ids[0], all_ids[-1]]}]))
    value = build_field_result(document, "title", s).values[0]
    assert value.provenance.pages == [1, 2]
    assert value.text == "Interpellazione Risposta"


def test_unknown_id_rejected(document):
    s = parse_selection("title", sel("known", [{"span_ids": ["p009-b001-s001"]}]))
    with pytest.raises(SelectionError, match="Unknown"):
        build_field_result(document, "title", s)


def test_wrong_order_rejected(document):
    a, b, *_ = ids(document)
    s = parse_selection("title", sel("known", [{"span_ids": [b, a]}]))
    with pytest.raises(SelectionError, match="order"):
        build_field_result(document, "title", s)


def test_overlapping_blocks_rejected(document):
    a, b, *_ = ids(document)
    s = parse_selection("submitters", sel("known", [{"span_ids": [a, b]}, {"span_ids": [b]}]))
    with pytest.raises(SelectionError):
        build_field_result(document, "submitters", s)


def test_unknown_with_ids_rejected():
    with pytest.raises(SelectionError):
        parse_selection("title", sel("unknown", [{"span_ids": ["p001-b001-s001"]}]))


def test_known_without_ids_rejected():
    with pytest.raises(SelectionError):
        parse_selection("title", sel("known", []))
    with pytest.raises(SelectionError):
        parse_selection("title", sel("partial", [{"span_ids": []}]))


def test_unknown_without_blocks_ok():
    assert parse_selection("title", sel("unknown", [])).status == "unknown"


def test_kind_enum_and_scope():
    with pytest.raises(SelectionError):
        parse_selection("question_or_request", sel("known", [{"span_ids": ["x"], "kind": "answer"}]))
    with pytest.raises(SelectionError):
        parse_selection("title", sel("known", [{"span_ids": ["x"], "kind": "question"}]))


def test_title_must_be_single_block(document):
    a, b, *_ = ids(document)
    s = parse_selection("title", sel("known", [{"span_ids": [a]}, {"span_ids": [b]}]))
    with pytest.raises(SelectionError, match="one block"):
        build_field_result(document, "title", s)


def test_non_json_rejected():
    with pytest.raises(SelectionError):
        parse_selection("title", "not json")


def test_request_body_contains_spans_and_strict_schema(document):
    body = build_request_body("m", "title", document)
    assert "[p001-b001-s001] Interpellazione" in body["messages"][1]["content"]
    assert "=== PAGE 2 ===" in body["messages"][1]["content"]
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["temperature"] == 0


def test_run_field_valid_and_logged(document):
    client = FakeClient({"status": "known", "reason": "r", "blocks": [{"span_ids": [ids(document)[0]]}]})
    record = run_field(client, "m", document, "title")
    assert record["outcome"] == "valid"
    assert record["payload_hash"] == payload_hash(client.bodies[0])
    assert record["request_body"] == client.bodies[0]
    assert record["usage"] == {"total_tokens": 5}


def test_failed_request_not_unknown_and_not_retried(document):
    client = FakeClient(error=TimeoutError("slow"))
    record = run_field(client, "m", document, "title")
    assert record["outcome"] == "failed" and record["result"] is None
    assert len(client.bodies) == 1


def test_run_documents_writes_files(document, tmp_path):
    client = FakeClient({"status": "unknown", "reason": "r", "blocks": []})
    records = run_documents(client, "m", [document], tmp_path / "out")
    assert len(records) == 3 and len(client.bodies) == 3
    assert "3/3 technically valid" in (tmp_path / "out" / "overview.md").read_text()
