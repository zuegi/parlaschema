from copy import deepcopy

import pytest
from pydantic import ValidationError

from openparl_extractor.schema import (
    CORE_FIELDS, DocumentExtraction, DocumentResult, Fact, NormalizedDate,
)


@pytest.mark.parametrize("key", [*CORE_FIELDS, "document_role", "schema_version"])
def test_all_fields_required(document_data, key):
    del document_data[key]
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


@pytest.mark.parametrize("version", ["1", "0.2", None])
def test_rejects_other_versions(document_data, version):
    document_data["schema_version"] = version
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


def test_preserves_original_and_source_scoped_normalization(document):
    data = document.model_dump_json()
    restored = DocumentExtraction.model_validate_json(data)
    assert restored == document
    assert restored.affair_type.value.original == "Interpellanza"
    assert restored.affair_type.value.normalized == "TI:interpellanza"
    assert restored.title.value.normalized is None
    assert restored.title.status == "known"
    assert restored.document_role.value.normalized == "executive_response"
    assert restored.decision.status == "unknown"


def test_keeps_distinct_original_types_without_translation(document_data):
    document_data["affair_type"]["value"]["original"] = "Interrogazione"
    document_data["affair_type"]["value"]["normalized"] = "TI:interrogazione"
    document_data["affair_type"]["value"]["sources"][0]["quote"] = "Interrogazione"
    result = DocumentExtraction.model_validate(document_data)
    assert result.affair_type.value.normalized != "TI:interpellanza"


@pytest.mark.parametrize("value", ["ZH:interpellanza", "interpellation", "TI:"])
def test_type_normalization_requires_matching_namespace(document_data, value):
    document_data["affair_type"]["value"]["normalized"] = value
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


def test_rejects_extra_fields(document_data):
    document_data["procedural_events"] = []
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


@pytest.mark.parametrize("sources", [[], None])
def test_facts_require_evidence(document_data, sources):
    document_data["title"]["value"]["sources"] = sources
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


@pytest.mark.parametrize("attribute,value", [
    ("quote", ""), ("quote", " \n"), ("page", 0), ("page", True),
    ("document_id", "100"), ("document_id", 101),
])
def test_evidence_invariants(document_data, attribute, value):
    document_data["title"]["value"]["sources"][0][attribute] = value
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


@pytest.mark.parametrize("field", [
    {"status": "unknown", "value": None},
    {"status": "unknown", "value": "invented", "reason": "not_in_document"},
    {"status": "known", "value": None},
    {"status": "known", "value": [], "reason": None},
])
def test_state_invariants(document_data, field):
    document_data["submitters"] = field
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


def test_partial_requires_collection_and_reason(document_data):
    document_data["title"]["status"] = "partial"
    document_data["title"]["reason"] = "ambiguous"
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


def test_partial_preserves_explicit_unnamed_members_without_inventing_people(document_data):
    field = document_data["submitters"]
    field.update(status="partial", reason="unenumerated_members")
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)
    field["sources"] = [{"document_id": 100, "quote": "Example Person and others", "page": None}]
    result = DocumentExtraction.model_validate(document_data)
    assert len(result.submitters.value) == 1
    assert result.submitters.reason == "unenumerated_members"


def test_joint_answers_and_unlinked_preamble(document):
    answers = document.executive_answer.value
    assert answers[0].question_links is None
    assert answers[1].question_links.target_ids == ["q1", "q2"]
    assert "a. Budget?" in document.question_or_request.value[0].text.original


@pytest.mark.parametrize("target_ids", [["missing"], ["q1", "q1"]])
def test_rejects_invalid_question_links(document_data, target_ids):
    document_data["executive_answer"]["value"][1]["question_links"]["target_ids"] = target_ids
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


def test_link_requires_evidence(document_data):
    document_data["executive_answer"]["value"][1]["question_links"]["sources"] = []
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


@pytest.mark.parametrize("field", ["question_or_request", "executive_answer", "dates"])
def test_duplicate_item_ids_rejected(document_data, field):
    document_data[field]["value"].append(deepcopy(document_data[field]["value"][0]))
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


@pytest.mark.parametrize("iso,precision", [
    ("2030", "year"), ("2030-04", "month"), ("2032-02-29", "day"),
])
def test_date_precision_roundtrip(iso, precision):
    value = NormalizedDate(iso=iso, precision=precision)
    assert NormalizedDate.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize("iso,precision", [
    ("2030-04-01", "month"), ("2030", "day"), ("2030-02-29", "day"),
    ("2030-13", "month"), ("0000", "year"), ("２０３０", "year"),
])
def test_invalid_dates_rejected(iso, precision):
    with pytest.raises(ValidationError):
        NormalizedDate(iso=iso, precision=precision)


def test_unknown_date_normalization_and_meaning_remain_unknown(document_data):
    value = document_data["dates"]["value"][0]
    value["value"]["normalized"] = None
    result = DocumentExtraction.model_validate(document_data)
    assert result.dates.value[0].meaning is None
    assert result.dates.value[0].value.original == "April 2030"


def test_date_meaning_requires_evidence(document_data):
    document_data["dates"]["value"][0]["meaning"] = {
        "original": "Adopted", "normalized": "executive_response_adopted", "sources": [],
    }
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


def test_decision_date_links_are_local(document_data):
    document_data["decision"] = {
        "status": "known", "value": [{
            "id": "decision1",
            "text": document_data["title"]["value"],
            "date_links": {
                "target_ids": ["missing"],
                "sources": document_data["title"]["value"]["sources"],
            },
        }],
    }
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)


def test_whitespace_original_rejected():
    with pytest.raises(ValidationError):
        Fact[str](original="  ", sources=[{"document_id": 100, "quote": "source"}])


def test_failure_does_not_produce_successful_unknowns():
    result = DocumentResult(
        document_id=100, state="failed", extraction=None,
        error={"code": "parse", "message": "No usable text"},
    )
    assert result.extraction is None


@pytest.mark.parametrize("state,has_extraction,has_error", [
    ("failed", True, True), ("failed", False, False),
    ("completed", True, True), ("completed", False, False),
    ("partial", True, False), ("partial", False, True),
])
def test_invalid_document_outcomes(document, state, has_extraction, has_error):
    with pytest.raises(ValidationError):
        DocumentResult(
            document_id=100, state=state,
            extraction=document if has_extraction else None,
            error={"code": "parse", "message": "Unreadable section"} if has_error else None,
        )


def test_partial_document_keeps_supported_extraction(document):
    result = DocumentResult(
        document_id=100, state="partial", extraction=document,
        error={"code": "incomplete_source", "message": "Unreadable chart"},
    )
    assert result.extraction == document


def test_document_outcome_ids_match(document):
    with pytest.raises(ValidationError):
        DocumentResult(document_id=101, state="completed", extraction=document, error=None)


@pytest.mark.parametrize("reason", ["unreadable", "incomplete_source"])
def test_incomplete_source_not_a_successful_unknown(document_data, reason):
    document_data["decision"]["reason"] = reason
    document = DocumentExtraction.model_validate(document_data)
    with pytest.raises(ValidationError, match="requires partial/failed outcome"):
        DocumentResult(document_id=100, state="completed", extraction=document, error=None)
    DocumentResult(
        document_id=100, state="partial", extraction=document,
        error={"code": "incomplete_source", "message": "Source coverage incomplete"},
    )


def test_revalidates_mutated_nested_instances(document):
    document.title.value.sources.clear()
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document)
