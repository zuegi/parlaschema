from typing import Generic, Literal, Self, TypeVar

from pydantic import model_validator

from openparl_extractor.schema import (
    CORE_FIELDS, DocumentError, DocumentRole,
    ExtractedField, IdentifiedItem, ItemLinks, NonBlank, NormalizedDate, PositiveId,
    SchemaModel, Sources, TypeCode, item_ids, iter_evidence,
)


SCHEMA_VERSION = "0.2"
DateMeaning = Literal[
    "document_date", "filed", "executive_response_adopted",
    "parliamentary_decision", "debated",
]
T = TypeVar("T")


class TextFact(SchemaModel):
    original: NonBlank
    sources: Sources


class Classification(SchemaModel, Generic[T]):
    value: T
    sources: Sources


class AffairType(TextFact):
    normalized: Classification[TypeCode] | None = None


class DateFact(TextFact):
    normalized: NormalizedDate | None = None


class Submitter(SchemaModel):
    name: TextFact
    kind: Classification[Literal["person", "organization"]] | None = None
    role: Classification[
        Literal["submitter", "co_submitter", "filing_signatory"]
    ] | None = None


class QuestionOrRequest(IdentifiedItem):
    text: TextFact
    kind: Classification[Literal["question", "request"]] | None = None


class ExecutiveAnswer(IdentifiedItem):
    text: TextFact
    question_links: ItemLinks | None = None


class AffairDate(IdentifiedItem):
    value: DateFact
    meaning: Classification[DateMeaning] | None = None


class ParliamentaryDecision(IdentifiedItem):
    text: TextFact
    actor: TextFact | None = None
    date_links: ItemLinks | None = None


class DocumentExtraction(SchemaModel):
    schema_version: Literal["0.2"]
    affair_id: PositiveId
    document_id: PositiveId
    parliament: NonBlank
    language: NonBlank
    document_role: ExtractedField[Classification[DocumentRole]]
    affair_type: ExtractedField[AffairType]
    title: ExtractedField[TextFact]
    submitters: ExtractedField[list[Submitter]]
    addressed_body: ExtractedField[list[TextFact]]
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
            if affair_type.normalized.value.split(":")[0] != self.parliament:
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
