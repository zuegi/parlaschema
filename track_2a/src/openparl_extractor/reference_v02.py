from collections.abc import Iterator
from typing import Literal, Self

from pydantic import BaseModel, model_validator

from openparl_extractor.reference import (
    HumanReview as HumanReviewV01, SourceIdentity,
)
from openparl_extractor.schema import CORE_FIELDS, ItemLinks, NormalizedDate, SchemaModel
from openparl_extractor.schema_v02 import Classification, DocumentExtraction, TextFact


class HumanReview(HumanReviewV01):
    review_version: Literal["0.2"]


def claim_paths(value: object, path: str = "") -> Iterator[str]:
    if isinstance(value, (TextFact, Classification, NormalizedDate, ItemLinks)):
        yield path
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from claim_paths(getattr(value, name), f"{path}/{name}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from claim_paths(item, f"{path}/{index}")


class ReferenceAnnotation(SchemaModel):
    reference_version: Literal["0.2"]
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
