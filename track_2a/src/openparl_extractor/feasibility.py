import hashlib
import json
from collections.abc import Sequence
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from openparl_extractor.provenance import validate_evidence
from openparl_extractor.reference import Assessment
from openparl_extractor.schema import (
    CORE_FIELDS, SCHEMA_VERSION, CoreFieldName, Evidence, NonBlank, PositiveId,
    Reason, SchemaModel,
)
from openparl_extractor.schema_export import export_schema

Sha256 = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]
Check = Literal["pass", "fail", "unassessed"]
QUALITY_GATE = 0.8


class SchemaIdentity(SchemaModel):
    version: NonBlank
    sha256: Sha256


def current_schema_identity() -> SchemaIdentity:
    return SchemaIdentity(
        version=SCHEMA_VERSION,
        sha256=hashlib.sha256(export_schema().encode("utf-8")).hexdigest(),
    )


class SourceAssessment(SchemaModel):
    status: Literal["unassessed", "absent", "present", "partial", "unreadable", "ambiguous"]
    reason: Reason | None = None
    rationale: NonBlank
    references: Annotated[list[NonBlank], Field(min_length=1)]
    sources: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_state(self) -> Self:
        reasons = {
            "unassessed": (None,), "absent": ("not_in_document",),
            "present": (None,), "partial": ("incomplete_source", "unenumerated_members"),
            "unreadable": ("unreadable",), "ambiguous": ("ambiguous",),
        }
        if self.reason not in reasons[self.status]:
            raise ValueError("source reason contradicts source status")
        if self.status in ("present", "partial", "ambiguous") and not self.sources:
            raise ValueError("observed content requires source evidence")
        return self


class RepresentationAssessment(SchemaModel):
    status: Literal["unassessed", "lossless", "partial_loss", "not_representable"]
    schema_elements: list[NonBlank] = Field(default_factory=list)
    rationale: NonBlank
    original_preserved: bool | None = None
    profile_required: bool | None = None

    @model_validator(mode="after")
    def validate_representation(self) -> Self:
        if self.status != "unassessed" and not self.schema_elements:
            raise ValueError("representation judgment requires concrete schema elements")
        if self.status == "lossless" and self.original_preserved is not True:
            raise ValueError("lossless requires preservation of original content")
        if self.status == "lossless" and self.profile_required is not False:
            raise ValueError("lossless cannot depend on an unavailable schema profile")
        return self


class ExtractionAssessment(SchemaModel):
    status: Literal["unassessed", "correct_present", "justified_unknown", "partial", "incorrect", "failed"]
    result_reference: NonBlank | None = None
    rationale: NonBlank
    technical_accepted: bool | None = None
    semantics: Assessment | None = None
    completeness: Check = "unassessed"
    original_fidelity: Check = "unassessed"
    evidence_exactness: Check = "unassessed"
    status_reason: Check = "unassessed"

    @model_validator(mode="after")
    def validate_extraction(self) -> Self:
        if self.status != "unassessed" and self.result_reference is None:
            raise ValueError("extraction judgment requires an unchanged result reference")
        if self.status == "failed" and self.technical_accepted is not False:
            raise ValueError("failed extraction cannot be technically accepted")
        if self.status in ("correct_present", "justified_unknown"):
            self.validate_full_credit()
        return self

    def validate_full_credit(self) -> None:
        if self.technical_accepted is not True or self.semantics is None:
            raise ValueError("full credit requires technical acceptance and semantic assessment")
        checks = (self.completeness, self.original_fidelity, self.evidence_exactness, self.status_reason)
        if any(check != "pass" for check in checks):
            raise ValueError("full credit requires every quality check to pass")
        if self.status == "correct_present":
            self.semantics.validate_present()
        elif (self.semantics.accuracy, self.semantics.support, self.semantics.unknown) != (
            "correct", None, "justified",
        ):
            raise ValueError("unknown credit requires correct/justified and no positive support claim")


class FeasibilityReview(SchemaModel):
    reviewer: NonBlank
    reviewer_kind: Literal["human"]
    reviewed_at: AwareDatetime
    verdict: Literal["confirmed", "needs_changes", "unresolved"]
    note: NonBlank


class FieldFeasibility(SchemaModel):
    assessment_version: Literal["0.1"] = "0.1"
    state: Literal["draft"] = "draft"
    origin: Literal["agent", "human"]
    document_id: PositiveId
    field: CoreFieldName
    schema_identity: SchemaIdentity
    source: SourceAssessment
    representation: RepresentationAssessment
    extraction: ExtractionAssessment
    review: FeasibilityReview | None = None

    @model_validator(mode="after")
    def validate_assessment(self) -> Self:
        if self.schema_identity != current_schema_identity():
            raise ValueError("assessment must bind to the current exact schema version/hash")
        self.validate_schema_elements()
        if any(source.document_id != self.document_id for source in self.source.sources):
            raise ValueError("assessment evidence must refer to this document")
        self.validate_axis_combination()
        return self

    def validate_schema_elements(self) -> None:
        schema = json.loads(export_schema())
        for pointer in self.representation.schema_elements:
            if not pointer.startswith("/"):
                raise ValueError("schema element must be a JSON pointer")
            value = schema
            for part in pointer[1:].split("/"):
                key = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(value, dict) or key not in value:
                    raise ValueError(f"unknown schema element: {pointer}")
                value = value[key]
        if self.representation.status != "unassessed":
            if f"/properties/{self.field}" not in self.representation.schema_elements:
                raise ValueError("representation must identify the assessed core field")

    def validate_axis_combination(self) -> None:
        status = self.extraction.status
        if self.source.status == "unassessed" and self.representation.status != "unassessed":
            raise ValueError("representation judgment requires assessed source content")
        if status in ("unassessed", "failed"):
            return
        if self.source.status == "unassessed" or self.representation.status == "unassessed":
            raise ValueError("semantic extraction assessment requires both prior axes")
        if status in ("correct_present", "justified_unknown"):
            if self.representation.status != "lossless":
                raise ValueError("full credit cannot hide a representation loss")
        if status == "correct_present" and self.source.status != "present":
            raise ValueError("positive full credit requires fully available source content")
        if status == "justified_unknown" and self.source.status not in ("absent", "ambiguous"):
            raise ValueError("unreadability or missed content cannot justify unknown credit")


def validate_assessment_sources(
    assessment: FieldFeasibility, documents: dict[int, tuple[str, ...]],
) -> None:
    for source in assessment.source.sources:
        validate_evidence(source, documents)


def _evaluation_denominator(
    assessments: Sequence[FieldFeasibility], document_ids: Sequence[int],
) -> int:
    expected = {(document_id, field) for document_id in document_ids for field in CORE_FIELDS}
    keys = [(item.document_id, item.field) for item in assessments]
    if not document_ids or len(set(document_ids)) != len(document_ids):
        raise ValueError("evaluation requires a nonempty unique frozen document list")
    if len(set(keys)) != len(keys) or not set(keys) <= expected:
        raise ValueError("duplicate or out-of-scope field assessments")
    return len(expected)


def summarize_fields(assessments: Sequence[FieldFeasibility], document_ids: Sequence[int]) -> dict[str, int | float | bool]:
    denominator = _evaluation_denominator(assessments, document_ids)
    confirmed = [item for item in assessments if item.review and item.review.verdict == "confirmed"]
    positive = sum(item.extraction.status == "correct_present" for item in confirmed)
    unknown = sum(item.extraction.status == "justified_unknown" for item in confirmed)
    resolved = sum(item.extraction.status != "unassessed" for item in confirmed)
    positive_opportunities = sum(item.source.status in ("present", "partial") for item in assessments)
    unknown_opportunities = sum(item.source.status in ("absent", "ambiguous") for item in assessments)
    return {
        "denominator": denominator, "recorded": len(assessments), "reviewed_resolved": resolved,
        "positive_full_credit": positive, "justified_unknown_credit": unknown,
        "positive_opportunities_draft": positive_opportunities,
        "unknown_opportunities_draft": unknown_opportunities,
        "positive_rate_draft": positive / positive_opportunities if positive_opportunities else 0.0,
        "unknown_rate_draft": unknown / unknown_opportunities if unknown_opportunities else 0.0,
        "full_field_points": positive + unknown, "score": (positive + unknown) / denominator,
        "coverage_complete": resolved == denominator,
        "quality_gate_passed": resolved == denominator and (positive + unknown) / denominator >= QUALITY_GATE,
    }
