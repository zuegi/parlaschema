import pytest
from pydantic import ValidationError

from openparl_extractor.reference import ReferenceAnnotation, claim_paths
from openparl_extractor.schema import CORE_FIELDS


PRESENT = {"accuracy": "correct", "support": "supported", "unknown": None}
UNKNOWN = {"accuracy": "correct", "support": None, "unknown": "justified"}


@pytest.fixture
def reference_data(document):
    return {
        "reference_version": "0.1", "candidate_origin": "machine_draft",
        "state": "draft", "extraction": document.model_dump(),
        "source": {"pdf_sha256": "0" * 64, "text_representation": "synthetic pages"},
        "publication_permission": "pending",
    }


@pytest.fixture
def review(document):
    return {
        "reviewer": "Synthetic human reviewer", "reviewer_kind": "human",
        "reviewed_at": "2030-04-01T10:00:00Z",
        "fields": {
            name: dict(UNKNOWN if getattr(document, name).status == "unknown" else PRESENT)
            for name in CORE_FIELDS
        },
        "document_role": dict(PRESENT),
        "items": {path: dict(PRESENT) for path in claim_paths(document)},
    }


def test_machine_candidate_stays_draft(reference_data):
    result = ReferenceAnnotation.model_validate(reference_data)
    assert result.state == "draft"
    assert result.review is None


def test_machine_draft_cannot_auto_approve(reference_data):
    reference_data["state"] = "approved"
    with pytest.raises(ValidationError, match="human review"):
        ReferenceAnnotation.model_validate(reference_data)


def test_human_review_does_not_authorize_publication(reference_data, review):
    reference_data.update(state="approved", review=review)
    result = ReferenceAnnotation.model_validate(reference_data)
    assert result.candidate_origin == "machine_draft"
    assert result.publication_permission == "pending"
    assert ReferenceAnnotation.model_validate_json(result.model_dump_json()) == result


def test_machine_reviewer_cannot_approve(reference_data, review):
    review["reviewer_kind"] = "machine"
    reference_data.update(state="approved", review=review)
    with pytest.raises(ValidationError, match="human review"):
        ReferenceAnnotation.model_validate(reference_data)


@pytest.mark.parametrize("missing", ["fields", "items"])
def test_approval_requires_complete_review(reference_data, review, missing):
    review[missing].pop(next(iter(review[missing])))
    reference_data.update(state="approved", review=review)
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_data)


@pytest.mark.parametrize("dimension,value", [
    ("accuracy", "incorrect"), ("accuracy", "unresolved"),
    ("support", "unsupported"), ("support", "unresolved"),
])
def test_incorrect_or_unsupported_claims_cannot_be_approved(reference_data, review, dimension, value):
    review["fields"]["title"][dimension] = value
    reference_data.update(state="approved", review=review)
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_data)


def test_unjustified_unknown_cannot_be_approved(reference_data, review):
    review["fields"]["decision"]["unknown"] = "unjustified"
    reference_data.update(state="approved", review=review)
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_data)


def test_explicit_unnamed_members_can_be_correctly_reviewed_partial(reference_data, review):
    field = reference_data["extraction"]["submitters"]
    field.update(status="partial", reason="unenumerated_members")
    field["sources"] = [{"document_id": 100, "quote": "Example Person and others"}]
    reference_data.update(state="approved", review=review)
    result = ReferenceAnnotation.model_validate(reference_data)
    assert result.extraction.submitters.status == "partial"
    assert len(result.extraction.submitters.value) == 1


def test_omitted_member_with_unresolved_review_cannot_be_approved(reference_data, review):
    reference_data["extraction"]["submitters"].update(
        status="partial", reason="incomplete_source"
    )
    review["fields"]["submitters"]["accuracy"] = "unresolved"
    reference_data.update(state="approved", review=review)
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_data)


def test_all_semantic_claims_and_links_have_review_paths(document):
    paths = set(claim_paths(document))
    assert "/document_role/value" in paths
    assert "/executive_answer/value/1/question_links" in paths
    assert "/dates/value/0/value" in paths


def test_rejected_requires_review(reference_data):
    reference_data["state"] = "rejected"
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_data)


def test_review_timestamp_must_be_timezone_aware(reference_data, review):
    review["reviewed_at"] = "2030-04-01T10:00:00"
    reference_data.update(state="approved", review=review)
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_data)
