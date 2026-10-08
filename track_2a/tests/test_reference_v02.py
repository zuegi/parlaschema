from copy import deepcopy

import pytest
from pydantic import ValidationError

from openparl_extractor.provenance import ProvenanceError
from openparl_extractor.provenance_v02 import validate_provenance
from openparl_extractor.reference import (
    ReferenceAnnotation as ReferenceAnnotationV01, claim_paths as old_paths,
)
from openparl_extractor.reference_v02 import ReferenceAnnotation, claim_paths
from openparl_extractor.schema import CORE_FIELDS, iter_evidence
from openparl_extractor.schema_v02 import DocumentExtraction


PRESENT = {"accuracy": "correct", "support": "supported", "unknown": None}
UNKNOWN = {"accuracy": "correct", "support": None, "unknown": "justified"}


@pytest.fixture
def reference_v02_data(document_v02):
    return {
        "reference_version": "0.2", "candidate_origin": "machine_draft",
        "state": "draft", "extraction": document_v02.model_dump(),
        "source": {"pdf_sha256": "0" * 64, "text_representation": "synthetic pages"},
        "publication_permission": "pending",
    }


@pytest.fixture
def review_v02(document_v02):
    return {
        "review_version": "0.2",
        "reviewer": "Synthetic human reviewer", "reviewer_kind": "human",
        "reviewed_at": "2030-04-01T10:00:00Z",
        "fields": {name: dict(PRESENT) for name in CORE_FIELDS},
        "document_role": dict(PRESENT),
        "items": {path: dict(PRESENT) for path in claim_paths(document_v02)},
    }


EXPECTED_PATHS = [
    "/document_role/value",
    "/affair_type/value",
    "/affair_type/value/normalized",
    "/title/value",
    "/submitters/value/0/name",
    "/submitters/value/0/kind",
    "/submitters/value/0/role",
    "/addressed_body/value/0",
    "/question_or_request/value/0/text",
    "/question_or_request/value/0/kind",
    "/executive_answer/value/0/text",
    "/executive_answer/value/0/question_links",
    "/decision/value/0/text",
    "/decision/value/0/actor",
    "/decision/value/0/date_links",
    "/dates/value/0/value",
    "/dates/value/0/value/normalized",
    "/dates/value/0/meaning",
    "/dates/value/1/value",
    "/dates/value/1/value/normalized",
    "/dates/value/1/meaning",
]


def test_paths_are_complete_ordered_and_roundtrip_deterministic(document_v02):
    assert list(claim_paths(document_v02)) == EXPECTED_PATHS
    restored = DocumentExtraction.model_validate_json(document_v02.model_dump_json())
    assert list(claim_paths(restored)) == EXPECTED_PATHS


@pytest.mark.parametrize("state", ["draft", "in_review"])
def test_unreviewed_candidate_cannot_become_approval(reference_v02_data, state):
    reference_v02_data["state"] = state
    result = ReferenceAnnotation.model_validate(reference_v02_data)
    assert result.review is None and result.state == state
    reference_v02_data["state"] = "approved"
    with pytest.raises(ValidationError, match="explicit human review"):
        ReferenceAnnotation.model_validate(reference_v02_data)


def test_explicit_complete_human_review_can_approve(reference_v02_data, review_v02):
    reference_v02_data.update(state="approved", review=review_v02)
    result = ReferenceAnnotation.model_validate(reference_v02_data)
    assert result.review.review_version == "0.2"
    assert result.publication_permission == "pending"
    assert ReferenceAnnotation.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("path", EXPECTED_PATHS)
def test_every_text_category_normalization_and_link_requires_assessment(
    reference_v02_data, review_v02, path,
):
    del review_v02["items"][path]
    reference_v02_data.update(state="approved", review=review_v02)
    with pytest.raises(ValidationError, match="every claim/link path"):
        ReferenceAnnotation.model_validate(reference_v02_data)


@pytest.mark.parametrize("path", [
    "/question_or_request/value/0", "/dates/value/0/value/precision",
    "/submitters/value/0/name/normalized", "/question_or_request/value/9/kind",
])
def test_wrong_or_extra_paths_rejected(reference_v02_data, review_v02, path):
    review_v02["items"][path] = dict(PRESENT)
    reference_v02_data.update(state="approved", review=review_v02)
    with pytest.raises(ValidationError, match="every claim/link path"):
        ReferenceAnnotation.model_validate(reference_v02_data)


@pytest.mark.parametrize("path", EXPECTED_PATHS)
@pytest.mark.parametrize("dimension,value", [
    ("accuracy", "incorrect"), ("accuracy", "unresolved"),
    ("support", "unsupported"), ("support", "unresolved"), ("unknown", "justified"),
])
def test_each_claim_is_attested_independently(reference_v02_data, review_v02, path,
                                             dimension, value):
    review_v02["items"][path][dimension] = value
    reference_v02_data.update(state="approved", review=review_v02)
    with pytest.raises(ValidationError, match="correct/supported"):
        ReferenceAnnotation.model_validate(reference_v02_data)


@pytest.mark.parametrize("missing", CORE_FIELDS)
def test_all_fields_require_review(reference_v02_data, review_v02, missing):
    del review_v02["fields"][missing]
    reference_v02_data.update(state="approved", review=review_v02)
    with pytest.raises(ValidationError, match="all eight core fields"):
        ReferenceAnnotation.model_validate(reference_v02_data)


def test_document_role_requires_its_own_valid_assessment(reference_v02_data, review_v02):
    review_v02["document_role"]["support"] = "unsupported"
    reference_v02_data.update(state="approved", review=review_v02)
    with pytest.raises(ValidationError, match="correct/supported"):
        ReferenceAnnotation.model_validate(reference_v02_data)


def test_optional_null_claims_are_not_assessed(reference_v02_data, review_v02):
    reference_v02_data["extraction"]["affair_type"]["value"]["normalized"] = None
    del review_v02["items"]["/affair_type/value/normalized"]
    reference_v02_data.update(state="approved", review=review_v02)
    assert ReferenceAnnotation.model_validate(reference_v02_data).state == "approved"


def test_justified_unknown_requires_correct_field_assessment(reference_v02_data, review_v02):
    reference_v02_data["extraction"]["decision"] = {
        "status": "unknown", "value": None, "reason": "not_in_document",
    }
    review_v02["items"] = {path: assessment for path, assessment in review_v02["items"].items()
                           if not path.startswith("/decision/")}
    review_v02["fields"]["decision"] = dict(UNKNOWN)
    reference_v02_data.update(state="approved", review=review_v02)
    assert ReferenceAnnotation.model_validate(reference_v02_data).state == "approved"
    review_v02["fields"]["decision"]["unknown"] = "unjustified"
    with pytest.raises(ValidationError, match="correct/justified"):
        ReferenceAnnotation.model_validate(reference_v02_data)


def test_correctly_reviewed_partial_keeps_collective_source(reference_v02_data, review_v02):
    field = reference_v02_data["extraction"]["submitters"]
    field.update(status="partial", reason="unenumerated_members",
                 sources=[{"document_id": 100, "quote": "Alex Example and others"}])
    reference_v02_data.update(state="approved", review=review_v02)
    result = ReferenceAnnotation.model_validate(reference_v02_data)
    assert result.extraction.submitters.status == "partial"
    review_v02["fields"]["submitters"]["accuracy"] = "unresolved"
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_v02_data)


@pytest.mark.parametrize("change", ["machine", "naive_timestamp", "no_role", "no_identity"])
def test_human_attestation_metadata_is_required(reference_v02_data, review_v02, change):
    if change == "machine":
        review_v02["reviewer_kind"] = "machine"
    elif change == "naive_timestamp":
        review_v02["reviewed_at"] = "2030-04-01T10:00:00"
    else:
        del review_v02["document_role" if change == "no_role" else "reviewer"]
    reference_v02_data.update(state="approved", review=review_v02)
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_v02_data)


def test_v01_reference_and_review_cannot_be_relabelled_as_v02(document, reference_v02_data):
    old_review = {
        "reviewer": "Synthetic old reviewer", "reviewer_kind": "human",
        "reviewed_at": "2030-04-01T10:00:00Z",
        "fields": {name: dict(UNKNOWN if getattr(document, name).status == "unknown" else PRESENT)
                   for name in CORE_FIELDS},
        "document_role": dict(PRESENT),
        "items": {},
    }
    old_review["items"] = {path: dict(PRESENT) for path in old_paths(document)}
    old = ReferenceAnnotationV01(
        reference_version="0.1", candidate_origin="machine_draft", state="approved",
        extraction=document, source=reference_v02_data["source"],
        publication_permission="pending", review=old_review,
    )
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(old.model_dump())
    relabelled = deepcopy(reference_v02_data)
    relabelled.update(state="approved", review=old.review.model_dump())
    with pytest.raises(ValidationError, match="review_version"):
        ReferenceAnnotation.model_validate(relabelled)
    relabelled["review"]["review_version"] = "0.2"
    with pytest.raises(ValidationError, match="correct/supported"):
        ReferenceAnnotation.model_validate(relabelled)
    relabelled["review"]["fields"] = {name: dict(PRESENT) for name in CORE_FIELDS}
    with pytest.raises(ValidationError, match="every claim/link path"):
        ReferenceAnnotation.model_validate(relabelled)


def test_review_does_not_substitute_for_each_claims_own_sources(reference_v02_data, review_v02):
    reference_v02_data.update(state="approved", review=review_v02)
    extraction = ReferenceAnnotation.model_validate(reference_v02_data).extraction
    documents = {100: ("\n".join(source.quote for source in iter_evidence(extraction)),)}
    reference_v02_data["extraction"]["question_or_request"]["value"][0]["kind"]["sources"][0][
        "quote"
    ] = "Invented classification evidence"
    reference = ReferenceAnnotation.model_validate(reference_v02_data)
    with pytest.raises(ProvenanceError, match="Quote not found"):
        validate_provenance(reference.extraction, documents)
    del reference_v02_data["extraction"]["question_or_request"]["value"][0]["kind"]["sources"]
    with pytest.raises(ValidationError):
        ReferenceAnnotation.model_validate(reference_v02_data)


def test_rejected_requires_review(reference_v02_data):
    reference_v02_data["state"] = "rejected"
    with pytest.raises(ValidationError, match="requires a review"):
        ReferenceAnnotation.model_validate(reference_v02_data)


def test_mutated_approved_review_is_revalidated(reference_v02_data, review_v02):
    reference_v02_data.update(state="approved", review=review_v02)
    reference = ReferenceAnnotation.model_validate(reference_v02_data)
    reference.review.items["/question_or_request/value/0/kind"].support = "unsupported"
    with pytest.raises(ValidationError, match="correct/supported"):
        ReferenceAnnotation.model_validate(reference)
