from collections.abc import Iterator
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

from openparl_extractor.schema import (
    CORE_FIELDS, CoreFieldName, DocumentExtraction, ExtractedField,
    Fact, ItemLinks, NonBlank, SchemaModel,
)


class Assessment(SchemaModel):
    accuracy: Literal["correct", "incorrect", "unresolved"]
    support: Literal["supported", "unsupported", "unresolved"] | None
    unknown: Literal["justified", "unjustified", "unresolved"] | None
    note: NonBlank | None = None

    def validate_present(self) -> None:
        if self.accuracy != "correct" or self.support != "supported" or self.unknown is not None:
            raise ValueError("approved present claims require correct/supported assessments")

    def validate_field(self, value: ExtractedField) -> None:
        if value.status != "unknown":
            self.validate_present()
        elif self.accuracy != "correct" or self.unknown != "justified" or self.support is not None:
            raise ValueError("approved unknown requires correct/justified and no support claim")


class HumanReview(SchemaModel):
    reviewer: NonBlank
    reviewer_kind: Literal["human", "machine"]
    reviewed_at: AwareDatetime
    fields: dict[CoreFieldName, Assessment]
    document_role: Assessment
    items: dict[NonBlank, Assessment]


def claim_paths(value: object, path: str = "") -> Iterator[str]:
    if isinstance(value, (Fact, ItemLinks)):
        yield path
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from claim_paths(getattr(value, name), f"{path}/{name}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from claim_paths(item, f"{path}/{index}")


class SourceIdentity(SchemaModel):
    pdf_sha256: Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]
    text_representation: NonBlank
    limitations: list[NonBlank] = Field(default_factory=list)


class ReferenceAnnotation(SchemaModel):
    reference_version: Literal["0.1"]
    candidate_origin: Literal["machine_draft", "human_authored"]
    state: Literal["draft", "in_review", "approved", "rejected"]
    extraction: DocumentExtraction
    source: SourceIdentity
    publication_permission: Literal["pending", "authorized", "denied"]
    review: HumanReview | None = None

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        if self.state == "approved":
            self.validate_approval()
        elif self.state == "rejected" and self.review is None:
            raise ValueError("rejected annotation requires a review")
        return self

    def validate_approval(self) -> None:
        review = self.review
        if review is None or review.reviewer_kind != "human":
            raise ValueError("approval requires an explicit human review")
        if set(review.fields) != set(CORE_FIELDS):
            raise ValueError("approval requires assessments of all eight core fields")
        for name in CORE_FIELDS:
            review.fields[name].validate_field(getattr(self.extraction, name))
        review.document_role.validate_field(self.extraction.document_role)
        if set(review.items) != set(claim_paths(self.extraction)):
            raise ValueError("approval requires assessments of every claim/link path")
        for assessment in review.items.values():
            assessment.validate_present()
