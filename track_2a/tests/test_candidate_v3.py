import copy
import json

import pytest

from openparl_extractor.candidate_run import DEVELOPMENT_DOCUMENTS
from openparl_extractor.candidate_v3 import (
    MAX_TOKENS, Selection, build_input, build_result, parse_selection, request_body,
)
from openparl_extractor.candidate_v3_run import MODEL, run_field, run_requests
from openparl_extractor.candidates import generate_candidates
from openparl_extractor.span_selection import SelectionError
from test_candidate_selection import FakeClient
from test_candidates import make_document


def fixture_data(field="submitters", blocks=None):
    document = make_document([blocks or [
        ["Betreffend: Bessere Schulen für alle"],
        ["Kantonsrätin Anna Muster, Zürich, hat folgende", "Anfrage eingereicht:"],
        ["1. Was kostet es?", "a. Erste Unterfrage?", "b. Zweite Unterfrage?"],
        ["2. Welche Mittel werden benötigt?"],
    ]])
    return document, build_input(document, generate_candidates(document), field)


def select(status="known", category="submitter", ids=("C1",), evidence=("E1",), reason=None, status_evidence=()):
    return Selection.model_validate({
        "status": status, "reason": reason, "status_evidence": list(status_evidence),
        "items": [{"id": cid, "category": category, "evidence": list(evidence)} for cid in ids],
    })


def test_role_uses_full_source_context_not_bare_name():
    document, data = fixture_data()
    assert data["values"][0]["text"] == "Anna Muster"
    assert "Anfrage eingereicht:" in data["evidence"][0]["text"]
    result = build_result(document, data, select())
    assert result["values"][0]["category"] == "submitter"
    assert result["values"][0]["text"] == "Anna Muster"
    assert result["values"][0]["evidence"][0]["origin"] == "source_block"


def test_context_not_selectable_original_replacement():
    _, data = fixture_data()
    assert all(v["kind"] != "context" for v in data["values"])
    assert all(v["text"] != e["text"] for v in data["values"] for e in data["evidence"])


def test_partial_unnamed_members_with_exact_group_evidence():
    document, data = fixture_data(blocks=[["à l'interpellation Marc Dupont et consorts - Sujet complet"]])
    result = build_result(document, data, select("partial", reason="unenumerated_members", status_evidence=("E1",)))
    assert result["status"] == "partial" and "et consorts" in result["status_evidence"][0]["text"]
    assert [v["text"] for v in result["values"]] == ["Marc Dupont"]
    with pytest.raises(SelectionError, match="unnamed group"):
        build_result(document, data, select())


def test_false_unnamed_group_claim_rejected():
    document, data = fixture_data()
    with pytest.raises(SelectionError, match="unnamed-group"):
        build_result(document, data, select("partial", reason="unenumerated_members", status_evidence=("E1",)))


def test_ambiguous_role_null_needs_review():
    document, data = fixture_data(blocks=[["I. Die Anfrage Anna Muster wird beantwortet:"]])
    assert not data["evidence"][0]["submission_context_hint"]
    result = build_result(document, data, select("needs_review", category=None, reason="ambiguous"))
    assert result["values"][0]["category"] is None
    with pytest.raises(SelectionError, match="explicit associated"):
        build_result(document, data, select())


def test_exact_names_with_same_explicit_context_grouped_as_alternative_sources():
    document, data = fixture_data(blocks=[["von Anna Muster (SP, Zürich)"], ["von Anna Muster (SP, Zürich)"]])
    assert len(data["values"]) == 1 and len(data["values"][0]["members"]) == 2
    assert data["values"][0]["evidence_ids"] == ["E1", "E2"]
    result = build_result(document, data, select(evidence=("E2",)))
    assert len(result["values"]) == 1 and result["values"][0]["alternative_members"]


@pytest.mark.parametrize("second", [
    "I. Die Anfrage Anna Muster wird beantwortet:",
    "von Anna Muster (FDP, Bern)",
    "Conseillère Anna Muster signe cette décision.",
])
def test_same_name_different_or_ambiguous_context_not_identity_fused(second):
    _, data = fixture_data(blocks=[["von Anna Muster (SP, Zürich)"], [second]])
    assert len(data["values"]) == 2
    assert all(len(v["members"]) == 1 for v in data["values"])


def test_duplicate_ungrouped_person_selection_rejected():
    document, data = fixture_data(blocks=[["von Anna Muster (SP, Zürich)"], ["von Anna Muster (FDP, Bern)"]])
    selection = Selection.model_validate({
        "status": "known", "reason": None, "status_evidence": [],
        "items": [{"id": "C1", "category": "submitter", "evidence": ["E1"]},
                  {"id": "C2", "category": "submitter", "evidence": ["E2"]}],
    })
    with pytest.raises(SelectionError, match="Duplicate person"):
        build_result(document, data, selection)


@pytest.mark.parametrize("eid", ["E999", "E2"])
def test_evidence_must_exist_and_belong_to_selected_candidate(eid):
    document, data = fixture_data(blocks=[["von Anna Muster"], ["von Hans Beispiel"]])
    with pytest.raises(SelectionError, match="not linked"):
        build_result(document, data, select(evidence=(eid,)))


@pytest.mark.parametrize("ids,evidence", [(("C999",), ("E1",)), (("C1", "C1"), ("E1",)), (("C1",), ())])
def test_invalid_ids_duplicates_empty_evidence(ids, evidence):
    document, data = fixture_data()
    with pytest.raises(SelectionError):
        build_result(document, data, select(ids=ids, evidence=evidence))


def test_questions_complete_parent_with_separate_kind_and_evidence():
    document, data = fixture_data("question_or_request")
    mains = [v for v in data["values"] if v["kind"] == "main_item"]
    selected = Selection.model_validate({
        "status": "known", "reason": None, "status_evidence": [],
        "items": [{"id": v["id"], "category": "question", "evidence": v["evidence_ids"]} for v in mains],
    })
    result = build_result(document, data, selected)
    assert len(result["values"]) == 2
    assert "a. Erste Unterfrage?" in result["values"][0]["text"]
    assert all(v["category"] == "question" for v in result["values"])
    for items in (list(reversed(selected.items)), [selected.items[0], selected.items[0]]):
        with pytest.raises(SelectionError):
            build_result(document, data, selected.model_copy(update={"items": items}))
    sub = data["values"][1]
    overlap = selected.model_copy(update={"items": [
        selected.items[0],
        selected.items[0].model_copy(update={"id": sub["id"], "evidence": sub["evidence_ids"]}),
    ]})
    with pytest.raises(SelectionError, match="overlaps"):
        build_result(document, data, overlap)


@pytest.mark.parametrize("field,category", [("title", "submitter"), ("submitters", "question"),
                                           ("question_or_request", "submitter")])
def test_incompatible_category_rejected(field, category):
    document, data = fixture_data(field)
    with pytest.raises(SelectionError, match="incompatible"):
        build_result(document, data, select(category=category))


def test_null_question_kind_requires_needs_review():
    document, data = fixture_data("question_or_request")
    with pytest.raises(SelectionError, match="Ambiguous category"):
        build_result(document, data, select(category=None))
    assert build_result(document, data, select("needs_review", category=None, reason="ambiguous"))["status"] == "needs_review"


@pytest.mark.parametrize("value", [
    {"status": "known", "reason": None, "status_evidence": [], "items": []},
    {"status": "partial", "reason": "unenumerated_members", "status_evidence": [], "items": []},
    {"status": "not_found", "reason": None, "status_evidence": [], "items": []},
    {"status": "needs_review", "reason": "not_found", "status_evidence": [], "items": []},
    {"status": "unknown", "reason": None, "status_evidence": [], "items": []},
])
def test_status_consistency_and_closed_enums(value):
    with pytest.raises(SelectionError):
        parse_selection(json.dumps(value))


def test_not_found_is_empty_search_claim_and_ambiguous_can_be_empty():
    document, data = fixture_data()
    for status, reason in (("not_found", "not_found"), ("needs_review", "ambiguous")):
        selection = Selection.model_validate({"status": status, "reason": reason, "status_evidence": [], "items": []})
        assert build_result(document, data, selection)["values"] == []


def test_tampered_provenance_rejected():
    document, data = fixture_data()
    data = copy.deepcopy(data)
    data["evidence"][0]["text"] = "made up"
    with pytest.raises(SelectionError, match="provenance"):
        build_result(document, data, select())


def test_length_complete_json_trailing_whitespace_vs_truncation():
    document, data = fixture_data()
    content = select().model_dump_json() + " " * 50
    client = FakeClient(content, "length")
    record = run_field(client, document, data, request_body(MODEL, data))
    assert record["outcome"] == "valid" and record["finish_reason"] == "length"
    client = FakeClient('{"status":"known","reason":null,"items":[', "length")
    assert run_field(client, document, data, request_body(MODEL, data))["outcome"] == "failed"
    assert len(client.bodies) == 1
    with pytest.raises(SelectionError):
        parse_selection(content + "prose")


def test_status_first_schema_budget_and_determinism():
    document, data = fixture_data()
    assert build_input(document, generate_candidates(document), "submitters") == data
    body = request_body(MODEL, data)
    schema = body["response_format"]["json_schema"]["schema"]
    assert list(schema["properties"])[0] == "status"
    assert schema["$defs"]["Item"]["properties"]["id"]["enum"] == ["C1"]
    assert body["temperature"] == 0 and body["top_p"] == 1
    assert body["max_tokens"] == MAX_TOKENS["submitters"]
    assert not {"stop", "guided_json"}.intersection(body)


def test_single_12_attempt_scope_fake_client(tmp_path):
    requests = []
    for did in DEVELOPMENT_DOCUMENTS:
        document, _ = fixture_data()
        document = document.model_copy(update={"document_id": did})
        for field in ("title", "submitters", "question_or_request"):
            data = build_input(document, generate_candidates(document), field)
            requests.append((document, data, request_body(MODEL, data)))
    client = FakeClient('{"status":"not_found","reason":"not_found","status_evidence":[],"items":[]}')
    records = run_requests(client, requests, tmp_path / "run")
    assert len(client.bodies) == len(records) == 12
    with pytest.raises(FileExistsError):
        run_requests(client, requests, tmp_path / "run")
    with pytest.raises(ValueError):
        run_requests(client, requests * 2, tmp_path / "other")
    assert len(client.bodies) == 12
