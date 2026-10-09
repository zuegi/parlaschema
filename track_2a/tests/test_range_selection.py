import json

import pymupdf
import pytest

from openparl_extractor.pdf_extraction import extract_source_document
from openparl_extractor.range_run import run_documents, run_field
from openparl_extractor.range_selection import (
    MAX_TOKENS,
    build_range_result,
    build_request_body,
    local_id_map,
    parse_json_object,
    parse_range_selection,
    render_local_lines,
)
from openparl_extractor.span_selection import SelectionError


@pytest.fixture
def document(tmp_path):
    pdf = pymupdf.open()
    page = pdf.new_page()
    for y, text in [(72, "Titel Teil eins"), (132, "Titel Teil zwei"), (192, "1. Frage eins"), (252, "2. Frage zwei")]:
        page.insert_text((72, y), text)
    page = pdf.new_page()
    page.insert_text((72, 72), "Fortsetzung Seite zwei")
    path = tmp_path / "d.pdf"
    pdf.save(path)
    return extract_source_document(path, 1)


def payload(status, ranges):
    return json.dumps({"status": status, "ranges": ranges}, separators=(",", ":"))


def rng(first, last, kind=None):
    return {"first": first, "last": last, "kind": kind}


class FakeClient:
    def __init__(self, content=None, finish_reason="stop", error=None):
        self.content, self.finish_reason, self.error, self.bodies = content, finish_reason, error, []

    def complete(self, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        choice = {"message": {"content": self.content}, "finish_reason": self.finish_reason}
        return {"choices": [choice], "usage": {"prompt_tokens": 1, "completion_tokens": 2}}


def test_local_ids_unique_and_mapped_to_stable_ids(document):
    mapping = local_id_map(document)
    assert list(mapping) == ["L1", "L2", "L3", "L4", "L5"]
    assert list(mapping.values()) == list(document.spans_by_id())
    assert "[L5] Fortsetzung Seite zwei" in render_local_lines(document)


def test_range_expands_across_page_boundary(document):
    selection = parse_range_selection("title", payload("known", [{"first": "L1", "last": "L5"}]))
    result = build_range_result(document, "title", selection)
    assert result.values[0].provenance.span_ids == list(document.spans_by_id())
    assert result.values[0].provenance.pages == [1, 2]
    assert "title spans 5 lines" in result.needs_review


def test_title_two_lines_no_review(document):
    selection = parse_range_selection("title", payload("known", [{"first": "L1", "last": "L2"}]))
    result = build_range_result(document, "title", selection)
    assert result.values[0].text == "Titel Teil eins Titel Teil zwei"
    assert result.needs_review == []


def test_questions_separate_ranges_and_number_removed(document):
    content = payload("known", [rng("L3", "L3", "question"), rng("L4", "L4", None)])
    result = build_range_result(document, "question_or_request", parse_range_selection("question_or_request", content))
    assert [v.text for v in result.values] == ["Frage eins", "Frage zwei"]
    assert [v.kind for v in result.values] == ["question", None]


@pytest.mark.parametrize("ranges", [[{"first": "L1", "last": "L9"}], [{"first": "L9", "last": "L9"}]])
def test_unknown_endpoint_rejected(document, ranges):
    selection = parse_range_selection("submitters", payload("known", ranges))
    with pytest.raises(SelectionError, match="Unknown local id"):
        build_range_result(document, "submitters", selection)


def test_reversed_range_rejected(document):
    selection = parse_range_selection("submitters", payload("known", [{"first": "L3", "last": "L2"}]))
    with pytest.raises(SelectionError, match="Reversed"):
        build_range_result(document, "submitters", selection)


def test_overlapping_and_unordered_ranges_rejected(document):
    for ranges in ([rng("L2", "L3"), rng("L3", "L4")], [rng("L4", "L4"), rng("L1", "L1")]):
        selection = parse_range_selection("question_or_request", payload("known", ranges))
        with pytest.raises(SelectionError, match="overlaps or precedes"):
            build_range_result(document, "question_or_request", selection)


def test_status_range_consistency():
    with pytest.raises(SelectionError):
        parse_range_selection("title", payload("not_found", [{"first": "L1", "last": "L1"}]))
    with pytest.raises(SelectionError):
        parse_range_selection("title", payload("known", []))
    assert parse_range_selection("title", payload("not_found", [])).status == "not_found"


def test_title_multiple_ranges_and_foreign_kind_rejected():
    with pytest.raises(SelectionError, match="single range"):
        parse_range_selection("title", payload("known", [rng("L1", "L1"), rng("L2", "L2")]))
    with pytest.raises(SelectionError, match="kind"):
        parse_range_selection("submitters", payload("known", [rng("L1", "L1", "question")]))


def test_complete_json_with_trailing_whitespace_parses():
    assert parse_json_object('{"a":1}' + " \n" * 500) == {"a": 1}


def test_truncated_json_and_extra_prose_rejected():
    with pytest.raises(SelectionError, match="truncated"):
        parse_json_object('{"status":"known","ranges":[' + " " * 100)
    with pytest.raises(SelectionError, match="Extra"):
        parse_json_object('{"a":1} Hope this helps')


def test_length_finish_with_complete_json_is_valid_and_recorded(document):
    client = FakeClient(payload("known", [{"first": "L1", "last": "L2"}]) + " " * 300, finish_reason="length")
    record = run_field(client, "m", document, "title")
    assert record["outcome"] == "valid" and record["finish_reason"] == "length"


def test_truncated_response_is_failed(document):
    record = run_field(FakeClient('{"status":"known","ranges":[{"first":"L1"', "length"), "m", document, "title")
    assert record["outcome"] == "failed" and record["finish_reason"] == "length"
    assert record["result"] is None


def test_request_error_failed_without_retry(document):
    client = FakeClient(error=TimeoutError("slow"))
    assert run_field(client, "m", document, "title")["outcome"] == "failed"
    assert len(client.bodies) == 1


def test_request_body_enums_and_field_token_limits(document):
    for field, limit in MAX_TOKENS.items():
        body = build_request_body("m", field, document)
        schema = body["response_format"]["json_schema"]["schema"]
        item = schema["properties"]["ranges"]["items"]
        assert item["properties"]["first"]["enum"] == ["L1", "L2", "L3", "L4", "L5"]
        assert body["max_tokens"] == limit and body["temperature"] == 0 and body["top_p"] == 1
        assert ("kind" in item["properties"]) == (field == "question_or_request")
    assert "[L1] Titel Teil eins" in body["messages"][1]["content"]


def test_run_documents_writes_new_dir_only(document, tmp_path):
    client = FakeClient(payload("not_found", []))
    out = tmp_path / "run"
    assert len(run_documents(client, "m", [document], out)) == 3
    assert "3/3 technically valid" in (out / "overview.md").read_text()
    with pytest.raises(FileExistsError):
        run_documents(client, "m", [document], out)
