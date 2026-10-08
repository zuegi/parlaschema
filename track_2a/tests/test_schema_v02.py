from copy import deepcopy
from typing import Literal

import pytest
from pydantic import ValidationError

from openparl_extractor.schema import (
    CORE_FIELDS, DocumentExtraction as DocumentExtractionV01, DocumentResult as DocumentResultV01,
)
from openparl_extractor.schema_v02 import (
    Classification, DateFact, DateMeaning, DocumentExtraction, DocumentResult, TextFact,
)


def test_roundtrip_keeps_text_and_interpretation_separate(document_v02):
    restored = DocumentExtraction.model_validate_json(document_v02.model_dump_json())
    assert restored == document_v02
    question = restored.question_or_request.value[0]
    assert question.text.original == "1. When will repairs start?\na. Budget?"
    assert question.kind.value == "question" and not hasattr(question.kind, "original")
    assert question.text.sources != question.kind.sources
    assert restored.dates.value[0].value.normalized.iso == "2030-05-02"
    assert restored.dates.value[1].meaning.value == "debated"
    assert restored.affair_type.value.normalized.value == "ZZ:interpellation"


@pytest.mark.parametrize("key", [*CORE_FIELDS, "document_role", "schema_version"])
def test_all_fields_remain_required(document_v02_data, key):
    del document_v02_data[key]
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


def test_versions_are_explicit_and_not_interchangeable(document_data, document_v02_data):
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_data)
    with pytest.raises(ValidationError):
        DocumentExtractionV01.model_validate(document_v02_data)


@pytest.mark.parametrize("model,data", [
    (TextFact, {"original": "Text", "sources": []}),
    (TextFact, {"original": " \n", "sources": [{"document_id": 100, "quote": "Text"}]}),
    (TextFact, {"original": "Text", "normalized": "Paraphrase",
                "sources": [{"document_id": 100, "quote": "Text"}]}),
    (Classification[Literal["question", "request"]], {"value": "question", "sources": []}),
    (Classification[Literal["question", "request"]], {"value": None,
        "sources": [{"document_id": 100, "quote": "Question?"}]}),
    (Classification[Literal["question", "request"]], {"value": "answer",
        "sources": [{"document_id": 100, "quote": "Question?"}]}),
    (Classification[Literal["question", "request"]], {"value": "question", "original": "Question?",
        "sources": [{"document_id": 100, "quote": "Question?"}]}),
])
def test_invalid_text_and_classification_shapes_rejected(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize("slot", ["kind", "role"])
def test_submitter_classifications_cannot_inherit_name_evidence(document_v02_data, slot):
    del document_v02_data["submitters"]["value"][0][slot]["sources"]
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


@pytest.mark.parametrize("field", ["document_role", "question_or_request", "dates", "affair_type"])
def test_each_interpretation_needs_own_sources(document_v02_data, field):
    value = document_v02_data[field]["value"]
    category = value if field == "document_role" else (
        value["normalized"] if field == "affair_type"
        else value[0]["kind" if field == "question_or_request" else "meaning"]
    )
    del category["sources"]
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


@pytest.mark.parametrize("field", ["title", "document_role"])
@pytest.mark.parametrize("attribute,value", [
    ("page", 0), ("page", True), ("document_id", 101), ("quote", " \n"),
])
def test_text_and_classification_evidence_invariants(document_v02_data, field, attribute, value):
    document_v02_data[field]["value"]["sources"][0][attribute] = value
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


@pytest.mark.parametrize("code", ["ZZ:interpellation", "ZZ:motion"])
def test_type_category_preserves_local_namespace(document_v02_data, code):
    document_v02_data["affair_type"]["value"]["normalized"]["value"] = code
    assert DocumentExtraction.model_validate(document_v02_data).affair_type.value.original \
        == "Interpellation"


@pytest.mark.parametrize("code", ["TI:interpellation", "interpellation", "ZZ:"])
def test_bad_type_namespace_or_shape_rejected(document_v02_data, code):
    document_v02_data["affair_type"]["value"]["normalized"]["value"] = code
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


@pytest.mark.parametrize("meaning", DateMeaning.__args__)
def test_date_meanings_are_explicit_categories(document_v02_data, meaning):
    document_v02_data["dates"]["value"][0]["meaning"]["value"] = meaning
    assert DocumentExtraction.model_validate(document_v02_data).dates.value[0].meaning.value \
        == meaning


@pytest.mark.parametrize("iso,precision", [
    ("2030", "year"), ("2030-04", "month"), ("2032-02-29", "day"),
])
def test_typed_date_normalization(iso, precision):
    fact = DateFact(original="Source date", normalized={"iso": iso, "precision": precision},
                    sources=[{"document_id": 100, "quote": "Source date"}])
    assert fact.normalized.precision == precision


@pytest.mark.parametrize("iso,precision", [
    ("2030-04-01", "month"), ("2030-02-29", "day"), ("２０３０", "year"),
])
def test_invalid_date_normalization_rejected(iso, precision):
    with pytest.raises(ValidationError):
        DateFact(original="Source date", normalized={"iso": iso, "precision": precision},
                 sources=[{"document_id": 100, "quote": "Source date"}])


def test_genuine_unknown_subclassifications_remain_nullable(document_v02_data):
    document_v02_data["question_or_request"]["value"][0]["kind"] = None
    document_v02_data["dates"]["value"][0]["meaning"] = None
    document_v02_data["dates"]["value"][0]["value"]["normalized"] = None
    document_v02_data["affair_type"]["value"]["normalized"] = None
    result = DocumentExtraction.model_validate(document_v02_data)
    assert result.question_or_request.value[0].kind is None
    assert result.dates.value[0].meaning is None


@pytest.mark.parametrize("field", [
    {"status": "unknown", "value": None},
    {"status": "unknown", "value": [], "reason": "not_in_document"},
    {"status": "known", "value": []},
    {"status": "partial", "value": [], "reason": "incomplete_source"},
])
def test_field_state_invariants_remain_strict(document_v02_data, field):
    document_v02_data["submitters"] = field
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


def test_partial_collective_mention_needs_its_own_evidence(document_v02_data):
    field = document_v02_data["submitters"]
    field.update(status="partial", reason="unenumerated_members")
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)
    field["sources"] = [{"document_id": 100, "quote": "Alex Example and others", "page": 1}]
    result = DocumentExtraction.model_validate(document_v02_data)
    assert len(result.submitters.value) == 1


@pytest.mark.parametrize("field", ["title", "document_role"])
def test_scalar_partial_rejected(document_v02_data, field):
    document_v02_data[field].update(status="partial", reason="ambiguous")
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


@pytest.mark.parametrize("field", ["question_or_request", "executive_answer", "decision", "dates"])
def test_duplicate_ids_rejected(document_v02_data, field):
    document_v02_data[field]["value"].append(deepcopy(document_v02_data[field]["value"][0]))
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


@pytest.mark.parametrize("field,link", [
    ("executive_answer", "question_links"), ("decision", "date_links"),
])
@pytest.mark.parametrize("targets,sources", [
    (["missing"], [{"document_id": 100, "quote": "Link"}]),
    (["q1", "q1"], [{"document_id": 100, "quote": "Link"}]), (["q1"], []),
])
def test_links_require_existing_unique_targets_and_evidence(document_v02_data, field, link,
                                                           targets, sources):
    document_v02_data[field]["value"][0][link] = {"target_ids": targets, "sources": sources}
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02_data)


def test_outcomes_keep_existing_failure_and_source_coverage_rules(document_v02):
    completed = DocumentResult(document_id=100, state="completed", extraction=document_v02,
                               error=None)
    assert DocumentResult.model_validate_json(completed.model_dump_json()) == completed
    failed = DocumentResult(document_id=100, state="failed", extraction=None,
                            error={"code": "parse", "message": "No usable text"})
    assert failed.extraction is None


def test_result_versions_cannot_silently_switch(document, document_v02):
    for result_type, extraction in ((DocumentResult, document),
                                    (DocumentResultV01, document_v02)):
        with pytest.raises(ValidationError):
            result_type(document_id=100, state="completed", extraction=extraction, error=None)


def test_outcome_document_id_must_match(document_v02):
    with pytest.raises(ValidationError, match="outcome document ID must match"):
        DocumentResult(document_id=101, state="completed", extraction=document_v02, error=None)


@pytest.mark.parametrize("state,has_extraction,has_error", [
    ("failed", True, True), ("failed", False, False),
    ("completed", True, True), ("completed", False, False),
    ("partial", True, False), ("partial", False, True),
])
def test_invalid_document_outcomes_rejected(document_v02, state, has_extraction, has_error):
    with pytest.raises(ValidationError):
        DocumentResult(document_id=100, state=state,
                       extraction=document_v02 if has_extraction else None,
                       error={"code": "parse", "message": "Unreadable"} if has_error else None)


@pytest.mark.parametrize("reason", ["unreadable", "incomplete_source"])
def test_source_limit_prevents_completed_outcome(document_v02_data, reason):
    document_v02_data["decision"] = {"status": "unknown", "value": None, "reason": reason}
    extraction = DocumentExtraction.model_validate(document_v02_data)
    with pytest.raises(ValidationError, match="requires partial/failed outcome"):
        DocumentResult(document_id=100, state="completed", extraction=extraction, error=None)
    DocumentResult(document_id=100, state="partial", extraction=extraction,
                   error={"code": "incomplete_source", "message": "Source incomplete"})


def test_revalidates_mutated_classification_sources(document_v02):
    document_v02.question_or_request.value[0].kind.sources.clear()
    with pytest.raises(ValidationError):
        DocumentExtraction.model_validate(document_v02)
