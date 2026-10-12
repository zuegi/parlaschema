import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from openparl_extractor.feasibility import (
    FieldFeasibility, current_schema_identity, summarize_fields, validate_assessment_sources,
)
from openparl_extractor.provenance import ProvenanceError
from openparl_extractor.schema import CORE_FIELDS


@pytest.fixture
def assessment_data():
    return {
        "origin": "agent", "document_id": 100, "field": "title",
        "schema_identity": current_schema_identity().model_dump(),
        "source": {
            "status": "present", "rationale": "Synthetic heading observed",
            "references": ["synthetic page 1"],
            "sources": [{"document_id": 100, "page": 1, "quote": "Example title"}],
        },
        "representation": {
            "status": "lossless", "schema_elements": ["/properties/title"],
            "rationale": "Scalar Fact retains original heading",
            "original_preserved": True, "profile_required": False,
        },
        "extraction": {
            "status": "unassessed", "rationale": "No converter evaluated",
        },
    }


def credit(status="correct_present"):
    return {
        "status": status, "result_reference": "synthetic result v1",
        "rationale": "Synthetic complete supported result", "technical_accepted": True,
        "semantics": {
            "accuracy": "correct", "support": "supported" if status == "correct_present" else None,
            "unknown": None if status == "correct_present" else "justified",
        },
        "completeness": "pass", "original_fidelity": "pass",
        "evidence_exactness": "pass", "status_reason": "pass",
    }


def human_review():
    return {
        "reviewer": "Synthetic reviewer", "reviewer_kind": "human",
        "reviewed_at": "2030-01-01T12:00:00Z", "verdict": "confirmed",
        "note": "Synthetic fixture, not an actual approval",
    }


def test_schema_hash_matches_unchanged_export():
    schema = Path(__file__).parents[1] / "schemas/extraction-v0.1.json"
    assert current_schema_identity().sha256 == hashlib.sha256(schema.read_bytes()).hexdigest()


def test_draft_roundtrip_is_not_gold(assessment_data):
    assessment_data["extraction"] = credit()
    result = FieldFeasibility.model_validate(assessment_data)
    assert result.state == "draft" and result.review is None
    assert FieldFeasibility.model_validate_json(result.model_dump_json()) == result
    assert summarize_fields([result], [100])["full_field_points"] == 0


@pytest.mark.parametrize("source_status,reason", [
    ("unassessed", None), ("absent", "not_in_document"), ("present", None),
    ("partial", "incomplete_source"), ("partial", "unenumerated_members"),
    ("unreadable", "unreadable"), ("ambiguous", "ambiguous"),
])
def test_source_states_remain_distinct(assessment_data, source_status, reason):
    assessment_data["source"].update(status=source_status, reason=reason)
    if source_status == "unassessed":
        assessment_data["representation"]["status"] = "unassessed"
    result = FieldFeasibility.model_validate(assessment_data)
    assert result.source.status == source_status


@pytest.mark.parametrize("source_status,reason", [
    ("absent", "unreadable"), ("unreadable", "not_in_document"), ("present", "ambiguous"),
])
def test_contradictory_source_reason_rejected(assessment_data, source_status, reason):
    assessment_data["source"].update(status=source_status, reason=reason)
    with pytest.raises(ValidationError, match="contradicts"):
        FieldFeasibility.model_validate(assessment_data)


def test_extraction_error_does_not_change_schema_judgment(assessment_data):
    assessment_data["extraction"] = {
        "status": "incorrect", "result_reference": "synthetic unmodified run",
        "rationale": "Model omitted heading", "semantics": {
            "accuracy": "incorrect", "support": "unresolved", "unknown": None,
        },
    }
    result = FieldFeasibility.model_validate(assessment_data)
    assert result.representation.status == "lossless"
    assert result.extraction.status == "incorrect"


@pytest.mark.parametrize("source_status,reason", [
    ("unreadable", "unreadable"), ("partial", "incomplete_source"), ("present", None),
])
def test_unknown_credit_cannot_hide_source_or_extraction_gap(assessment_data, source_status, reason):
    assessment_data["source"].update(status=source_status, reason=reason)
    assessment_data["extraction"] = credit("justified_unknown")
    with pytest.raises(ValidationError, match="cannot justify"):
        FieldFeasibility.model_validate(assessment_data)


@pytest.mark.parametrize("source_status,reason", [
    ("absent", "not_in_document"), ("ambiguous", "ambiguous"),
])
def test_justified_unknown_separate_from_positive(assessment_data, source_status, reason):
    assessment_data["source"].update(status=source_status, reason=reason)
    assessment_data["extraction"] = credit("justified_unknown")
    assessment_data["review"] = human_review()
    score = summarize_fields([FieldFeasibility.model_validate(assessment_data)], [100])
    assert score["justified_unknown_credit"] == 1
    assert score["positive_full_credit"] == 0
    assert score["denominator"] == 8 and score["quality_gate_passed"] is False


@pytest.mark.parametrize("changes", [
    {"original_preserved": False}, {"profile_required": True}, {"schema_elements": []},
    {"schema_elements": ["/properties/not_a_field"]},
    {"schema_elements": ["/properties/dates"]},
])
def test_lossless_cannot_hide_original_loss_or_profile_need(assessment_data, changes):
    assessment_data["representation"].update(changes)
    with pytest.raises(ValidationError):
        FieldFeasibility.model_validate(assessment_data)


@pytest.mark.parametrize("status", ["partial_loss", "not_representable", "unassessed"])
def test_schema_limits_are_diagnostic_not_success(assessment_data, status):
    assessment_data["representation"].update(status=status, original_preserved=False)
    assert FieldFeasibility.model_validate(assessment_data).representation.status == status
    assessment_data["extraction"] = credit()
    with pytest.raises(ValidationError):
        FieldFeasibility.model_validate(assessment_data)


def test_unassessed_source_prevents_semantic_extraction_judgment(assessment_data):
    assessment_data["source"].update(status="unassessed")
    assessment_data["representation"]["status"] = "unassessed"
    assessment_data["extraction"].update(
        status="incorrect", result_reference="synthetic result",
    )
    with pytest.raises(ValidationError, match="prior axes"):
        FieldFeasibility.model_validate(assessment_data)


def test_operational_failure_can_precede_semantic_assessment(assessment_data):
    assessment_data["source"]["status"] = "unassessed"
    assessment_data["representation"]["status"] = "unassessed"
    assessment_data["extraction"].update(
        status="failed", result_reference="synthetic timeout", technical_accepted=False,
    )
    result = FieldFeasibility.model_validate(assessment_data)
    assert summarize_fields([result], [100, 101])["denominator"] == 16


def test_source_unreadability_is_not_positive_full_credit(assessment_data):
    assessment_data["source"].update(status="unreadable", reason="unreadable")
    assessment_data["extraction"] = credit()
    with pytest.raises(ValidationError, match="fully available"):
        FieldFeasibility.model_validate(assessment_data)


def test_source_and_extraction_partials_stay_in_denominator(assessment_data):
    assessment_data["source"].update(status="partial", reason="unenumerated_members")
    assessment_data["extraction"].update(
        status="partial", result_reference="synthetic unchanged partial",
    )
    assessment_data["review"] = human_review()
    score = summarize_fields([FieldFeasibility.model_validate(assessment_data)], [100])
    assert score["denominator"] == 8 and score["full_field_points"] == 0
    assert score["positive_opportunities_draft"] == 1 and score["positive_rate_draft"] == 0


@pytest.mark.parametrize("check", [
    "completeness", "original_fidelity", "evidence_exactness", "status_reason",
])
def test_full_credit_requires_all_checks(assessment_data, check):
    assessment_data["extraction"] = credit()
    assessment_data["extraction"][check] = "fail"
    with pytest.raises(ValidationError, match="every quality check"):
        FieldFeasibility.model_validate(assessment_data)


@pytest.mark.parametrize("key,value", [("version", "future"), ("sha256", "0" * 64)])
def test_stale_schema_binding_rejected(assessment_data, key, value):
    assessment_data["schema_identity"][key] = value
    with pytest.raises(ValidationError, match="exact schema"):
        FieldFeasibility.model_validate(assessment_data)


@pytest.mark.parametrize("change", [
    {"state": "approved"}, {"review": {**human_review(), "reviewer_kind": "machine"}},
    {"review": {**human_review(), "reviewed_at": "2030-01-01T12:00:00"}},
])
def test_agent_cannot_create_approval(assessment_data, change):
    assessment_data.update(change)
    with pytest.raises(ValidationError):
        FieldFeasibility.model_validate(assessment_data)


def test_source_quotes_use_existing_provenance_checker(assessment_data):
    result = FieldFeasibility.model_validate(assessment_data)
    validate_assessment_sources(result, {100: ("Example title",)})
    with pytest.raises(ProvenanceError, match="Quote not found"):
        validate_assessment_sources(result, {100: ("Different title",)})
    assessment_data["source"]["sources"][0]["document_id"] = 101
    with pytest.raises(ValidationError, match="this document"):
        FieldFeasibility.model_validate(assessment_data)


def test_frozen_denominator_missing_failed_and_partial_remain(assessment_data):
    assessment_data["extraction"] = credit()
    assessment_data["review"] = human_review()
    result = FieldFeasibility.model_validate(assessment_data)
    score = summarize_fields([result], [100, 101])
    assert score["denominator"] == 16 and score["score"] == 1 / 16
    assert score["coverage_complete"] is False
    with pytest.raises(ValueError, match="duplicate"):
        summarize_fields([result, result], [100])
    with pytest.raises(ValueError, match="out-of-scope"):
        summarize_fields([result], [101])
    with pytest.raises(ValueError, match="unique"):
        summarize_fields([], [100, 100])


def test_eighty_percent_gate_not_replaced(assessment_data):
    records = []
    for document_id in (100, 101, 102, 103, 104):
        for field in CORE_FIELDS:
            data = {
                **assessment_data, "document_id": document_id, "field": field,
                "source": {**assessment_data["source"], "sources": [
                    {"document_id": document_id, "quote": "Example title"},
                ]},
                "representation": {
                    **assessment_data["representation"], "schema_elements": [f"/properties/{field}"],
                },
                "extraction": credit() if document_id != 104 else {
                    "status": "failed", "result_reference": "synthetic failure",
                    "technical_accepted": False, "rationale": "Synthetic failure",
                },
                "review": human_review(),
            }
            records.append(FieldFeasibility.model_validate(data))
    score = summarize_fields(records, [100, 101, 102, 103, 104])
    assert score["denominator"] == 40 and score["score"] == 0.8
    assert score["quality_gate_passed"] is True
    records.pop()
    assert summarize_fields(records, [100, 101, 102, 103, 104])["quality_gate_passed"] is False
