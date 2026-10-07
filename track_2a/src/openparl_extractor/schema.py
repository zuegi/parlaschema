from collections.abc import Iterator, Sequence
from datetime import date
from typing import Annotated, Generic, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


SCHEMA_VERSION = "0.1"
CORE_FIELDS = (
    "affair_type", "title", "submitters", "addressed_body",
    "question_or_request", "executive_answer", "decision", "dates",
)
NonBlank = Annotated[str, StringConstraints(strict=True, pattern=r"\S")]
PositiveId = Annotated[int, Field(strict=True, gt=0)]
CoreFieldName = Literal[
    "affair_type", "title", "submitters", "addressed_body",
    "question_or_request", "executive_answer", "decision", "dates",
]
Reason = Literal[
    "not_in_document", "ambiguous", "unreadable",
    "incomplete_source", "unenumerated_members",
]
DocumentRole = Literal["filing", "executive_response", "other"]
DateMeaning = Literal[
    "document_date", "filed", "executive_response_adopted", "parliamentary_decision",
]
TypeCode = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Z][A-Z0-9_-]*:[a-z][a-z0-9_-]*$")
]
T = TypeVar("T")


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class Evidence(SchemaModel):
    document_id: PositiveId
    quote: NonBlank
    page: PositiveId | None = None


Sources = Annotated[list[Evidence], Field(min_length=1)]


class Fact(SchemaModel, Generic[T]):
    original: NonBlank
    normalized: T | None = None
    sources: Sources


class ExtractedField(SchemaModel, Generic[T]):
    status: Literal["known", "partial", "unknown"]
    value: T | None
    reason: Reason | None = None
    sources: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.status == "unknown":
            if self.value is not None or self.reason is None:
                raise ValueError("unknown requires null value and a reason")
        elif self.value is None or self.value == []:
            raise ValueError("known/partial requires a nonempty value")
        elif self.status == "known" and self.reason is not None:
            raise ValueError("known cannot have an unknown/partial reason")
        elif self.status == "partial":
            self.validate_partial()
        return self

    def validate_partial(self) -> None:
        if not isinstance(self.value, list) or self.reason in (None, "not_in_document"):
            raise ValueError("partial requires a collection and a partial-coverage reason")
        if self.reason == "unenumerated_members" and not self.sources:
            raise ValueError("unenumerated members require collective-mention evidence")


class Submitter(SchemaModel):
    name: Fact[NonBlank]
    kind: Fact[Literal["person", "organization"]] | None = None
    role: Fact[Literal["submitter", "co_submitter", "filing_signatory"]] | None = None


class IdentifiedItem(SchemaModel):
    id: NonBlank


class QuestionOrRequest(IdentifiedItem):
    text: Fact[NonBlank]
    kind: Fact[Literal["question", "request"]] | None = None


class ItemLinks(SchemaModel):
    target_ids: Annotated[list[NonBlank], Field(min_length=1)]
    sources: Sources

    @model_validator(mode="after")
    def validate_unique_targets(self) -> Self:
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("link target IDs must be unique")
        return self


class ExecutiveAnswer(IdentifiedItem):
    text: Fact[NonBlank]
    question_links: ItemLinks | None = None


class NormalizedDate(SchemaModel):
    iso: NonBlank
    precision: Literal["day", "month", "year"]

    @model_validator(mode="after")
    def validate_precision(self) -> Self:
        parts = {"day": 3, "month": 2, "year": 1}[self.precision]
        lengths = {"day": 10, "month": 7, "year": 4}
        if len(self.iso) != lengths[self.precision] or len(self.iso.split("-")) != parts:
            raise ValueError("ISO date must match declared precision")
        if not all(part.isascii() and part.isdigit() for part in self.iso.split("-")):
            raise ValueError("ISO date must contain ASCII date components")
        padded = self.iso + {"day": "", "month": "-01", "year": "-01-01"}[self.precision]
        date.fromisoformat(padded)
        return self


class AffairDate(IdentifiedItem):
    value: Fact[NormalizedDate]
    meaning: Fact[DateMeaning] | None = None


class ParliamentaryDecision(IdentifiedItem):
    text: Fact[NonBlank]
    actor: Fact[NonBlank] | None = None
    date_links: ItemLinks | None = None


def iter_evidence(value: object) -> Iterator[Evidence]:
    if isinstance(value, Evidence):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from iter_evidence(getattr(value, name))
    elif isinstance(value, list):
        for item in value:
            yield from iter_evidence(item)


def item_ids(items: Sequence[IdentifiedItem] | None) -> set[str]:
    ids = [item.id for item in (items or [])]
    if len(ids) != len(set(ids)):
        raise ValueError("item IDs must be unique within each collection")
    return set(ids)


class DocumentExtraction(SchemaModel):
    schema_version: Literal["0.1"]
    affair_id: PositiveId
    document_id: PositiveId
    parliament: NonBlank
    language: NonBlank
    document_role: ExtractedField[Fact[DocumentRole]]
    affair_type: ExtractedField[Fact[TypeCode]]
    title: ExtractedField[Fact[NonBlank]]
    submitters: ExtractedField[list[Submitter]]
    addressed_body: ExtractedField[list[Fact[NonBlank]]]
    question_or_request: ExtractedField[list[QuestionOrRequest]]
    executive_answer: ExtractedField[list[ExecutiveAnswer]]
    decision: ExtractedField[list[ParliamentaryDecision]]
    dates: ExtractedField[list[AffairDate]]

    @model_validator(mode="after")
    def validate_document_scope(self) -> Self:
        if any(source.document_id != self.document_id for source in iter_evidence(self)):
            raise ValueError("all evidence must refer to this document")
        affair_type = self.affair_type.value
        if affair_type and affair_type.normalized:
            if affair_type.normalized.split(":")[0] != self.parliament:
                raise ValueError("normalized affair type namespace must match parliament")
        self.validate_links()
        return self

    def validate_links(self) -> None:
        questions = item_ids(self.question_or_request.value)
        dates = item_ids(self.dates.value)
        item_ids(self.executive_answer.value)
        item_ids(self.decision.value)
        for answer in self.executive_answer.value or []:
            if answer.question_links and not set(answer.question_links.target_ids) <= questions:
                raise ValueError("answer links must reference local question IDs")
        for decision in self.decision.value or []:
            if decision.date_links and not set(decision.date_links.target_ids) <= dates:
                raise ValueError("decision links must reference local date IDs")


class DocumentError(SchemaModel):
    code: Literal["retrieval", "parse", "incomplete_source", "invalid_output", "provenance"]
    message: NonBlank


class DocumentResult(SchemaModel):
    document_id: PositiveId
    state: Literal["completed", "partial", "failed"]
    extraction: DocumentExtraction | None
    error: DocumentError | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.state == "failed":
            if self.extraction is not None or self.error is None:
                raise ValueError("failed requires error and no accepted extraction")
        elif self.extraction is None:
            raise ValueError("completed/partial requires extraction")
        elif (self.state == "completed") != (self.error is None):
            raise ValueError("completed has no error; partial requires error")
        if self.extraction and self.document_id != self.extraction.document_id:
            raise ValueError("outcome document ID must match extraction")
        self.validate_source_outcome()
        return self

    def validate_source_outcome(self) -> None:
        if self.state != "completed" or self.extraction is None:
            return
        for name in (*CORE_FIELDS, "document_role"):
            if getattr(self.extraction, name).reason in ("unreadable", "incomplete_source"):
                raise ValueError("unreadable/incomplete source requires partial/failed outcome")
