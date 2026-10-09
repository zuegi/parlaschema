import copy
import json

import pytest

from openparl_extractor.selection_coverage import (
    Selection, build_input, build_result, parse_selection, project_v4,
)
from openparl_extractor.source_document import Page, ReadabilityWarning
from openparl_extractor.span_selection import SelectionError
from openparl_extractor.selection_coverage_run import _replay
from test_candidate_selection import FakeClient
from test_candidate_v4 import inputs


def fixture(field="submitters", blocks=None):
    document, frozen = inputs(field, blocks)
    return document, build_input(document, frozen)


def selection(cid="C1", eid="E1", interpretation="submitter"):
    return Selection(items=[{"id": cid, "evidence": [eid], "interpretation": interpretation}])


def test_fake_client_nonempty_original_role_and_separate_coverage():
    document, data = fixture()
    client = FakeClient('{"items":[{"id":"C1","evidence":["E1"],"interpretation":"submitter"}]}')
    response = client.complete({"input": data})
    result = build_result(document, data, parse_selection(response["choices"][0]["message"]["content"]))
    assert result["selection_state"] == "selection_present"
    assert result["original_values"][0]["text"] == data["values"][0]["text"]
    assert result["categories"][0]["origin"] == "model_interpretation"
    assert result["coverage"]["semantic_coverage"] == "unverified"
    assert result["coverage"]["semantic_review"] is None
    assert "status" not in result and len(client.bodies) == 1


def test_empty_is_no_selection_not_unknown_absent():
    document, data = fixture()
    result = build_result(document, data, Selection(items=[]))
    assert result["selection_state"] == "no_selection"
    assert result["original_values"] == []
    assert result["coverage"]["semantic_coverage"] == "unverified"
    assert result["coverage"]["machine_coverage"]["selected"] == 0
    assert not result["coverage"]["machine_coverage"]["model_attention_verified"]


def test_code_kind_and_evidence_are_not_model_category():
    document, data = fixture("question_or_request")
    result = build_result(document, data, selection(interpretation=None))
    assert result["categories"][0]["category"] == "question"
    assert result["categories"][0]["origin"] == "code-derived"
    assert result["categories"][0]["evidence_ids"] == ["E1"]
    assert "a. Erste Unterfrage?" in result["original_values"][0]["text"]
    with pytest.raises(SelectionError, match="redundantly"):
        build_result(document, data, selection(interpretation="question"))


def test_heuristic_gap_not_claimed_as_genuine_ambiguity():
    document, data = fixture("question_or_request", [["1. Bericht zu den Massnahmen."]])
    result = build_result(document, data, selection(interpretation=None))
    assert result["categories"][0]["origin"] == "heuristic_gap_or_ambiguity_unverified"
    assert result["coverage"]["unclassified_candidates"] == ["C1"]
    assert result["coverage"]["open_interpretations"]
    with pytest.raises(SelectionError, match="separately verifiable"):
        build_result(document, data, selection(interpretation="request"))


def test_all_candidates_selected_still_unverified_and_not_attention_proof():
    document, data = fixture("question_or_request", [["1. Welche Mittel stehen bereit?"], ["2. Wie geht es weiter?"]])
    chosen = Selection(items=[{"id": v["id"], "evidence": v["evidence_ids"]} for v in data["values"]])
    coverage = build_result(document, data, chosen)["coverage"]
    assert all(v["selected"] for v in coverage["candidate_ledger"])
    assert coverage["machine_coverage"]["input_candidates_validated"] == 2
    assert coverage["semantic_coverage"] == "unverified" and coverage["semantic_review"] is None


def test_unpresented_page_and_no_text_layer_warning_not_absence():
    document, frozen = inputs()
    blank = Page(number=2, blocks=())
    warning = ReadabilityWarning(page=2, code="no_text_layer", message="OCR not run")
    document = document.model_copy(update={"pages": (*document.pages, blank), "warnings": (warning,)})
    data = build_input(document, frozen)
    coverage = build_result(document, data, Selection(items=[]))["coverage"]
    assert coverage["unpresented_source_pages"] == [2]
    assert coverage["source_inventory"]["warnings"][0]["message"] == "OCR not run"
    assert coverage["source_inventory"]["pdf_page_count_verified"] is False
    assert coverage["semantic_coverage"] == "unverified"
    broken = copy.deepcopy(data)
    broken["source_inventory"]["pages"].pop()
    with pytest.raises(SelectionError, match="inventory"):
        build_result(document, broken, Selection(items=[]))


@pytest.mark.parametrize("selected", [False, True])
def test_consopts_limit_without_completeness_or_fabricated_person(selected):
    document, data = fixture(blocks=[["à l'interpellation Marc Dupont et consorts - Sujet complet"]])
    result = build_result(document, data, selection() if selected else Selection(items=[]))
    assert result["coverage"]["group_limits"][0]["selected_person"] == selected
    assert len(result["original_values"]) == int(selected)
    assert result["coverage"]["semantic_coverage"] == "unverified"
    assert "partial" not in result and "known" not in result


@pytest.mark.parametrize("cid,eid", [("C999", "E1"), ("C1", "E999")])
def test_invalid_ids_not_ignored(cid, eid):
    document, data = fixture()
    with pytest.raises(SelectionError):
        build_result(document, data, selection(cid, eid))


def test_parent_child_and_duplicate_candidates_never_fixed():
    document, data = fixture("question_or_request")
    parent = {"id": "C1", "evidence": ["E1"]}
    for other in (parent, {"id": "C2", "evidence": ["E2"]}):
        with pytest.raises(SelectionError, match="duplicate|overlaps"):
            build_result(document, data, Selection(items=[parent, other]))


def test_duplicate_person_from_different_contexts_and_unfit_role():
    document, data = fixture(blocks=[["ANFRAGE", "von Marc Dupont"], ["Presentata da: Marc Dupont"]])
    assert len(data["values"]) == 2
    chosen = Selection(items=[{"id": v["id"], "evidence": v["evidence_ids"],
                              "interpretation": "submitter"} for v in data["values"]])
    with pytest.raises(SelectionError, match="Duplicate person"):
        build_result(document, data, chosen)
    document, data = fixture()
    bad = copy.deepcopy(data)
    source = bad["evidence"][0]
    source["submission_context_hint"] = False
    with pytest.raises(SelectionError, match="hint differs"):
        build_result(document, bad, selection())
    source.update({k: data["values"][0]["members"][0][k]
                   for k in ("text", "start", "end", "span_ids", "pages")})
    with pytest.raises(SelectionError, match="explicit"):
        build_result(document, bad, selection())


@pytest.mark.parametrize("change", ["text", "kind", "offset", "parent"])
def test_input_integrity_not_trusted(change):
    document, data = fixture("question_or_request")
    changed = copy.deepcopy(data)
    value = changed["values"][0]
    if change == "text":
        value["text"] += "invented"
    elif change == "kind":
        value["kind"] = "request"
    elif change == "offset":
        value["members"][0]["end"]["offset"] += 1
    else:
        value["child_ids"] = []
    with pytest.raises((SelectionError, ValueError)):
        build_result(document, changed, selection(interpretation=None))


def test_replay_drops_redundancy_but_retains_discarded_decision():
    document, data = fixture("question_or_request")
    raw = {"items": [{"id": "C1", "category": None, "evidence": ["E1"]}],
           "status": "not_found", "reason": "not_found", "status_evidence": []}
    before = copy.deepcopy(raw)
    chosen, diagnostic = project_v4(raw, data)
    result = build_result(document, data, chosen)
    assert raw == before
    assert diagnostic["discarded_model_decision"]["status"] == "not_found"
    assert result["coverage"]["semantic_coverage"] == "unverified"
    raw["items"][0]["category"] = "request"
    with pytest.raises(SelectionError, match="contradicts"):
        project_v4(raw, data)
    raw["items"][0]["category"] = None
    raw["status_evidence"] = ["E999"]
    with pytest.raises(SelectionError, match="discarded"):
        project_v4(raw, data)


def test_truncation_trailing_whitespace_and_old_status_not_in_transport():
    content = '{"items":[]} \n\t'
    assert parse_selection(content).items == []
    for bad in ('{"items":[', '{"items":[],"status":"known"}',
                '{"items":[],"semantic_coverage":"known-complete"}'):
        with pytest.raises(SelectionError):
            parse_selection(bad)
    assert json.loads(content)["items"] == []


def test_offline_replay_not_new_model_result_and_failed_overlap_reported():
    document, data = fixture("question_or_request")
    raw = {"items": [{"id": "C1", "category": None, "evidence": ["E1"]}],
           "status": "not_found", "reason": "not_found", "status_evidence": []}
    replay = _replay(document, data, raw)
    assert replay["diagnostic_only"] and replay["projection"]["diagnostic_only"]
    assert replay["integrity"] == "validated"
    assert replay["coverage"]["semantic_review"] is None
    raw["items"].append({"id": "C2", "category": None, "evidence": ["E2"]})
    failed = _replay(document, data, raw)
    assert failed["integrity"] == "failed" and failed["result"] is None
    assert failed["coverage"]["semantic_coverage"] == "unverified"


def test_ocr_source_inventory_is_visible_without_success_claim():
    document, frozen = inputs()
    page = document.pages[0]
    block = page.blocks[0]
    span = block.spans[0].model_copy(update={"source": "ocr"})
    block = block.model_copy(update={"spans": (span, *block.spans[1:])})
    page = page.model_copy(update={"blocks": (block, *page.blocks[1:])})
    document = document.model_copy(update={"pages": (page, *document.pages[1:])})
    data = build_input(document, frozen)
    result = build_result(document, data, Selection(items=[]))
    assert "ocr" in result["coverage"]["source_inventory"]["pages"][0]["sources"]
    assert result["coverage"]["semantic_coverage"] == "unverified"
