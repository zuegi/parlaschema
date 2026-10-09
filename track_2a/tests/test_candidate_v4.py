import json

import pytest

from openparl_extractor.candidate_v4 import (
    Selection, build_input, build_result, classify_kind, parse_selection, request_body,
)
from openparl_extractor.candidates import generate_candidates
from openparl_extractor.span_selection import SelectionError
from test_candidate_selection import FakeClient
from test_candidate_v3 import fixture_data
from test_candidates import make_document


def inputs(field="submitters", blocks=None):
    document, _ = fixture_data(field, blocks)
    return document, build_input(document, generate_candidates(document), field)


def selection(category="submitter", cid="C1", eid="E1", status="known", reason=None, status_ids=("E1",)):
    return Selection.model_validate({
        "status": status, "reason": reason, "status_evidence": list(status_ids),
        "items": [{"id": cid, "category": category, "evidence": [eid]}],
    })


def test_positive_known_status_evidence_and_property_order_fake_client():
    document, data = inputs()
    value = selection().model_dump()
    content = json.dumps({key: value[key] for key in ("items", "status_evidence", "reason", "status")})
    client = FakeClient(content)
    response = client.complete(request_body("fake", data))
    result = build_result(document, data, parse_selection(response["choices"][0]["message"]["content"]))
    assert result["status"] == "known" and result["status_evidence"][0]["id"] == "E1"
    assert len(client.bodies) == 1


@pytest.mark.parametrize("text,kind", [
    ("Wie lange dauert das Verfahren?", "question"),
    ("Quel bilan le Conseil d'État tire-t-il des projets?", "question"),
    ("Selon le Conseil d'État, quels sont les avantages?", "question"),
    ("Le Conseil d’État prévoit-il des soutiens?", "question"),
    ("Come valuta il Consiglio di Stato il calo?", "question"),
    ("Il Cantone dispone di dati?", "question"),
    ("Der Regierungsrat wird aufgefordert, Massnahmen zu ergreifen.", "request"),
    ("Le Conseil d'État est invité à présenter un rapport.", "request"),
    ("Si chiede di presentare un rapporto.", "request"),
    ("Die Überschrift nennt das Projekt?", None),
    ("Durchschnittliche Behandlungsdauer Schritt 1", None),
    ("Welche Möglichkeiten bestehen", None),
    ("Der Regierungsrat wird ersucht: Welche Mittel stehen bereit?", None),
])
def test_conservative_source_kind(text, kind):
    assert classify_kind(text)[0] == kind


def test_explicit_kind_missing_or_wrong_is_not_repaired():
    document, data = inputs("question_or_request")
    assert data["values"][0]["kind"] == "question"
    for category in (None, "request"):
        with pytest.raises(SelectionError, match="closed source classification"):
            build_result(document, data, selection(category=category))
    assert build_result(document, data, selection(category="question"))["values"][0]["category"] == "question"


def test_ambiguous_candidate_null_needs_review_only():
    document, data = inputs("question_or_request", [["1. Bericht zu den Massnahmen."], ["2. Ein weiterer Bericht."]])
    assert data["values"][0]["allowed_kinds"] == [None]
    result = build_result(document, data, selection(None, status="needs_review", reason="ambiguous"))
    assert result["values"][0]["category"] is None
    with pytest.raises(SelectionError, match="Ambiguous category"):
        build_result(document, data, selection(None))
    with pytest.raises(SelectionError, match="closed source classification"):
        build_result(document, data, selection("question"))


def test_parent_subitem_overlap_never_merged():
    document, data = inputs("question_or_request")
    parent = data["values"][0]
    assert parent["child_ids"] == ["C2", "C3"]
    response = selection("question").model_dump()
    response["items"].append({"id": "C2", "category": None, "evidence": ["E2"]})
    response.update(status="needs_review", reason="ambiguous")
    with pytest.raises(SelectionError, match="Parent and contained"):
        build_result(document, data, Selection.model_validate(response))
    assert "a. Erste Unterfrage?" in build_result(document, data, selection("question"))["values"][0]["text"]


def test_child_does_not_establish_complete_parent():
    document, data = inputs("question_or_request")
    with pytest.raises(SelectionError, match="Subitems alone"):
        build_result(document, data, selection(None, "C2", "E2", status_ids=("E2",)))


def test_consopts_group_hint_partial_consistency():
    document, data = inputs(blocks=[["à l'interpellation Marc Dupont et consorts - Sujet complet"]])
    assert data["group_hints"] == [{"candidate_id": "C1", "evidence_id": "E1", "limit": "unenumerated_members"}]
    with pytest.raises(SelectionError, match="requires partial"):
        build_result(document, data, selection())
    result = build_result(document, data, selection(status="partial", reason="unenumerated_members"))
    assert result["status"] == "partial"
    assert result["values"][0]["text"] == "Marc Dupont"
    with pytest.raises(SelectionError):
        build_result(document, data, selection(status="needs_review", reason="ambiguous"))


def test_full_title_vs_contained_fragment_no_document_special_case():
    document, data = inputs("title", [
        ["à l'interpellation Marc Dupont - Des solutions pour les"],
        ["emballages ? (26_INT_10)"],
    ])
    assert [(v["title_role"], v["text"]) for v in data["values"]] == [
        ("heading_fragment", "Des solutions pour les"),
        ("full_title", "Des solutions pour les\n\nemballages ?"),
    ]
    with pytest.raises(SelectionError, match="fragment"):
        build_result(document, data, selection(None))
    assert build_result(document, data, selection(None, "C2", "E2", status_ids=("E2",)))["values"][0]["text"].endswith("emballages ?")


@pytest.mark.parametrize("cid,eid", [("C999", "E1"), ("C1", "E999")])
def test_invalid_ids_and_evidence(cid, eid):
    document, data = inputs()
    with pytest.raises(SelectionError):
        build_result(document, data, selection(cid=cid, eid=eid))


def test_unknown_status_not_silently_mapped():
    value = selection().model_dump()
    value["status"] = "unknown"
    with pytest.raises(SelectionError):
        parse_selection(json.dumps(value))
    valid = parse_selection('{"status":"not_found","reason":"not_found","status_evidence":[],"items":[]}')
    assert valid.items == []


def test_truncation_vs_complete_trailing_whitespace_fake_client():
    document, data = inputs()
    client = FakeClient(selection().model_dump_json() + " \n " * 50, "length")
    response = client.complete(request_body("fake", data))
    assert build_result(document, data, parse_selection(response["choices"][0]["message"]["content"]))["status"] == "known"
    for content in ('{"items":[', selection().model_dump_json() + "prose"):
        with pytest.raises(SelectionError):
            parse_selection(content)
    assert len(client.bodies) == 1


def test_input_and_original_value_determinism():
    document, data = inputs()
    assert data == build_input(document, generate_candidates(document), "submitters")
    result = build_result(document, data, selection())
    assert result["values"][0]["text"] == "Anna Muster"
    assert request_body("fake", data)["messages"][0]["content"].find("property order is irrelevant") >= 0
