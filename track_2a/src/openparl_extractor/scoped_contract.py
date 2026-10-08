from collections.abc import Iterator
from typing import Annotated, Generic, Literal, Self, TypeVar

from pydantic import BaseModel, Field, model_validator

from openparl_extractor.provenance import validate_evidence
from openparl_extractor.schema import (
    DocumentRole, Evidence, ExtractedField, NonBlank, NormalizedDate, PositiveId,
    SchemaModel, TypeCode, iter_evidence,
)
from openparl_extractor.schema_v02 import (
    AffairDate, AffairType, Classification, DateMeaning, QuestionOrRequest, Submitter, TextFact,
)


METADATA_FIELDS = (
    "document_role", "affair_type", "title", "submitters", "addressed_body", "dates",
)
UNPROCESSED_FIELDS = ("executive_answer", "decision")
Offset = Annotated[int, Field(strict=True, ge=0)]
T = TypeVar("T")


class SourceDocument(SchemaModel):
    affair_id: PositiveId
    document_id: PositiveId
    parliament: NonBlank
    language: NonBlank
    pages: Annotated[list[str], Field(min_length=1)]


class Span(SchemaModel):
    page: PositiveId
    start: Offset
    end: Offset

    def text(self, source: SourceDocument) -> str:
        if self.page > len(source.pages):
            raise ValueError("span page outside document")
        page = source.pages[self.page - 1]
        if not self.start < self.end <= len(page):
            raise ValueError("span offsets outside page")
        text = page[self.start:self.end]
        if not text.strip():
            raise ValueError("span is blank")
        return text

    def evidence(self, source: SourceDocument) -> Evidence:
        return Evidence(document_id=source.document_id, page=self.page, quote=self.text(source))


SpanSources = Annotated[list[Span], Field(min_length=1)]
TEXT_SEGMENT_SEPARATOR = "\n\n"


def validate_span_order(spans: list[Span]) -> None:
    for previous, current in zip(spans, spans[1:]):
        if current.page < previous.page or (
            current.page == previous.page and current.start < previous.end
        ):
            raise ValueError("text segments must be nonoverlapping and in source order")


class TextSelection(SchemaModel):
    text_spans: SpanSources
    sources: SpanSources

    @model_validator(mode="after")
    def validate_segments(self) -> Self:
        validate_span_order(self.text_spans)
        return self

    def resolve(self, source: SourceDocument) -> dict:
        original = TEXT_SEGMENT_SEPARATOR.join(span.text(source) for span in self.text_spans)
        for selected in self.text_spans:
            if not any(span.page == selected.page and span.start <= selected.start
                       and span.end >= selected.end for span in self.sources):
                raise ValueError("text evidence must cover the complete selected text segments")
        return {"original": original, "sources": [span.evidence(source) for span in self.sources]}


class CategorySelection(SchemaModel, Generic[T]):
    value: T
    sources: SpanSources


class TypeSelection(TextSelection):
    normalized: CategorySelection[TypeCode] | None


class DateSelection(TextSelection):
    normalized: NormalizedDate | None


class SubmitterSelection(SchemaModel):
    name: TextSelection
    kind: CategorySelection[Literal["person", "organization"]] | None
    role: CategorySelection[Literal["submitter", "co_submitter", "filing_signatory"]] | None


class DateItemSelection(SchemaModel):
    id: NonBlank
    value: DateSelection
    meaning: CategorySelection[DateMeaning] | None


class QuestionSelection(SchemaModel):
    id: NonBlank
    text: TextSelection
    kind: CategorySelection[Literal["question", "request"]] | None


class SelectedField(SchemaModel, Generic[T]):
    status: Literal["known", "partial", "unknown"]
    value: T | None
    reason: Literal[
        "not_in_document", "ambiguous", "unreadable", "incomplete_source", "unenumerated_members",
    ] | None
    sources: list[Span]


class MetadataSelection(SchemaModel):
    document_role: SelectedField[CategorySelection[DocumentRole]]
    affair_type: SelectedField[TypeSelection]
    title: SelectedField[TextSelection]
    submitters: SelectedField[list[SubmitterSelection]]
    addressed_body: SelectedField[list[TextSelection]]
    dates: SelectedField[list[DateItemSelection]]


class QuestionsSelection(SchemaModel):
    question_or_request: SelectedField[list[QuestionSelection]]

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        items = self.question_or_request.value or []
        validate_span_order([item.text.text_spans[0] for item in items])
        segments = [span for item in items for span in item.text.text_spans]
        validate_span_order(sorted(segments, key=lambda span: (span.page, span.start)))
        return self


class ControlSelection(MetadataSelection, QuestionsSelection):
    pass


class MetadataExtraction(SchemaModel):
    document_role: ExtractedField[Classification[DocumentRole]]
    affair_type: ExtractedField[AffairType]
    title: ExtractedField[TextFact]
    submitters: ExtractedField[list[Submitter]]
    addressed_body: ExtractedField[list[TextFact]]
    dates: ExtractedField[list[AffairDate]]


class QuestionsExtraction(SchemaModel):
    question_or_request: ExtractedField[list[QuestionOrRequest]]


def resolve(value: object, source: SourceDocument) -> object:
    if isinstance(value, Span):
        return value.evidence(source)
    if isinstance(value, TextSelection):
        data = value.resolve(source)
        if isinstance(value, (TypeSelection, DateSelection)):
            data["normalized"] = resolve(value.normalized, source)
        return data
    if isinstance(value, BaseModel):
        return {name: resolve(getattr(value, name), source) for name in type(value).model_fields}
    if isinstance(value, list):
        return [resolve(item, source) for item in value]
    return value


def collection_ids(value: object) -> Iterator[list[str]]:
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from collection_ids(getattr(value, name))
    elif isinstance(value, list):
        ids = [item.id for item in value if isinstance(item, (AffairDate, QuestionOrRequest))]
        if ids:
            yield ids


def validate_task(extraction: MetadataExtraction | QuestionsExtraction,
                  source: SourceDocument) -> None:
    for evidence in iter_evidence(extraction):
        if evidence.document_id != source.document_id:
            raise ValueError("all evidence must refer to this document")
        validate_evidence(evidence, {source.document_id: tuple(source.pages)})
    if any(len(ids) != len(set(ids)) for ids in collection_ids(extraction)):
        raise ValueError("item IDs must be unique within each collection")
    if isinstance(extraction, MetadataExtraction):
        affair_type = extraction.affair_type.value
        if affair_type and affair_type.normalized:
            if affair_type.normalized.value.split(":")[0] != source.parliament:
                raise ValueError("normalized affair type namespace must match parliament")


class TaskError(SchemaModel):
    code: Literal["http", "timeout", "network", "invalid_output", "input", "incomplete_source"]
    message: NonBlank


class TaskResult(SchemaModel, Generic[T]):
    state: Literal["accepted", "partial", "failed"]
    extraction: T | None
    error: TaskError | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.state == "accepted":
            if self.extraction is None or self.error is not None:
                raise ValueError("accepted task requires extraction and no error")
        elif self.state == "partial":
            if self.extraction is None or self.error is None:
                raise ValueError("partial task requires extraction and error")
        elif self.extraction is not None or self.error is None:
            raise ValueError("failed task requires error and no extraction")
        if self.state == "accepted" and isinstance(self.extraction, BaseModel):
            for name in type(self.extraction).model_fields:
                if getattr(self.extraction, name).reason in ("unreadable", "incomplete_source"):
                    raise ValueError("source limits require partial task outcome")
        return self


def scope_state(metadata: TaskResult, questions: TaskResult) -> Literal["accepted", "partial", "failed"]:
    if metadata.state == questions.state == "accepted":
        return "accepted"
    return "partial" if metadata.extraction is not None or questions.extraction is not None else "failed"


class ScopeResult(SchemaModel):
    scope_version: Literal["0.2"]
    affair_id: PositiveId
    document_id: PositiveId
    parliament: NonBlank
    language: NonBlank
    state: Literal["accepted", "partial", "failed"]
    unprocessed_fields: tuple[Literal["executive_answer"], Literal["decision"]]
    metadata: TaskResult[MetadataExtraction]
    questions: TaskResult[QuestionsExtraction]

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        tasks = (self.metadata, self.questions)
        expected = scope_state(self.metadata, self.questions)
        if self.state != expected:
            raise ValueError("scope state must reflect both task outcomes")
        for task in tasks:
            if any(evidence.document_id != self.document_id
                   for evidence in iter_evidence(task.extraction)):
                raise ValueError("merged evidence must refer to this document")
            if any(len(ids) != len(set(ids)) for ids in collection_ids(task.extraction)):
                raise ValueError("merged item IDs must be unique within each collection")
        metadata = self.metadata.extraction
        if metadata and metadata.affair_type.value and metadata.affair_type.value.normalized:
            if metadata.affair_type.value.normalized.value.split(":")[0] != self.parliament:
                raise ValueError("merged type namespace must match parliament")
        return self
