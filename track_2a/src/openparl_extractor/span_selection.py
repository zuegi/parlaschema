import json
import re
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from openparl_extractor.source_document import SourceDocument, SourceDocumentError, reconstruct_text

FieldName = Literal["title", "submitters", "question_or_request"]
FIELD_NAMES: tuple[FieldName, ...] = ("title", "submitters", "question_or_request")
Status = Literal["known", "partial", "unknown"]
Kind = Literal["question", "request"]
LEADING_NUMBER = re.compile(r"^(?:\d+[a-z]?|[a-z])[.)]\s+")

FIELD_INSTRUCTIONS: dict[FieldName, str] = {
    "title": (
        "Select the spans that form the complete title of the parliamentary affair, not just a "
        "label such as 'Interpellation' or a reference number. "
    ),
    "submitters": (
        "Select the spans naming the persons who submitted the affair, one block per submitter. "
        "Exclude executive signatories (government, council, chancellery). Do not invent "
        "unnamed co-signatories; if only some submitters are identifiable use status 'partial'. "
    ),
    "question_or_request": (
        "Select the spans containing the questions or requests put by the submitters, one block "
        "per independently numbered question or request. Never merge separate numbered items; "
        "list sub-questions (1a, 1b, ...) as separate blocks. Set kind to 'question' or "
        "'request' only if unambiguous, otherwise null. Do not select answers. "
    ),
}
COMMON_INSTRUCTIONS = (
    "You receive the text of a Swiss parliamentary document as spans, each prefixed with its id "
    "in brackets. Return ONLY span ids, never text. Status 'unknown' only if the information is "
    "truly absent from the document, with no span ids. Status 'known' or 'partial' needs at "
    "least one span id. Within and across blocks, ids must be in document order without repeats. "
    "Do not infer anything that is not stated. Give a short reason in the document's language."
)


class SelectionError(ValueError):
    pass


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    span_ids: list[str]
    kind: Kind | None = None


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status
    reason: str
    blocks: list[Block]

    @model_validator(mode="after")
    def check_status_consistency(self) -> "Selection":
        has_ids = any(block.span_ids for block in self.blocks)
        if self.status == "unknown" and (has_ids or self.blocks):
            raise ValueError("unknown must not have blocks or span ids")
        if self.status != "unknown" and (not self.blocks or not all(b.span_ids for b in self.blocks)):
            raise ValueError(f"{self.status} needs blocks with at least one span id each")
        return self


class Provenance(BaseModel):
    pages: list[int]
    span_ids: list[str]
    text: str


class SelectedValue(BaseModel):
    text: str
    kind: Kind | None = None
    provenance: Provenance


class FieldResult(BaseModel):
    field: FieldName
    status: Status
    reason: str
    values: list[SelectedValue]


def response_schema(field: FieldName) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "object",
        "properties": {"span_ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["span_ids"],
        "additionalProperties": False,
    }
    if field == "question_or_request":
        block["properties"]["kind"] = {"type": ["string", "null"], "enum": ["question", "request", None]}
        block["required"].append("kind")
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["known", "partial", "unknown"]},
            "reason": {"type": "string"},
            "blocks": {"type": "array", "items": block},
        },
        "required": ["status", "reason", "blocks"],
        "additionalProperties": False,
    }


def render_spans(document: SourceDocument) -> str:
    lines: list[str] = []
    for page in document.pages:
        lines.append(f"=== PAGE {page.number} ===")
        for block in page.blocks:
            lines.extend(f"[{span.id}] {span.text.rstrip()}" for span in block.spans)
    return "\n".join(lines)


def build_request_body(model: str, field: FieldName, document: SourceDocument, max_tokens: int = 2048) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": COMMON_INSTRUCTIONS},
            {"role": "user", "content": f"Field: {field}\n{FIELD_INSTRUCTIONS[field]}\n\n{render_spans(document)}"},
        ],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": f"{field}_selection", "strict": True, "schema": response_schema(field)},
        },
    }


def parse_selection(field: FieldName, content: str) -> Selection:
    try:
        selection = Selection.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as error:
        raise SelectionError(f"Invalid selection output: {error}") from error
    if field != "question_or_request" and any(block.kind for block in selection.blocks):
        raise SelectionError(f"kind not allowed for {field}")
    return selection


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def derive_text(document: SourceDocument, field: FieldName, span_ids: Sequence[str]) -> str:
    text = normalize_whitespace(reconstruct_text(document, span_ids))
    return LEADING_NUMBER.sub("", text) if field == "question_or_request" else text


def _check_blocks_disjoint_and_ordered(document: SourceDocument, selection: Selection) -> None:
    order = {sid: position for position, sid in enumerate(document.spans_by_id())}
    flat = [sid for block in selection.blocks for sid in block.span_ids]
    unknown = [sid for sid in flat if sid not in order]
    if unknown:
        raise SelectionError(f"Unknown span ids: {', '.join(unknown)}")
    positions = [order[sid] for sid in flat]
    if any(later <= earlier for earlier, later in zip(positions, positions[1:])):
        raise SelectionError("Span ids duplicated, overlapping or not in document order across blocks")


def build_field_result(document: SourceDocument, field: FieldName, selection: Selection) -> FieldResult:
    _check_blocks_disjoint_and_ordered(document, selection)
    if field == "title" and len(selection.blocks) > 1:
        raise SelectionError("title must be a single block")
    lookup = document.spans_by_id()
    values = []
    for block in selection.blocks:
        try:
            text = derive_text(document, field, block.span_ids)
        except SourceDocumentError as error:
            raise SelectionError(str(error)) from error
        pages = sorted({lookup[sid][0].page for sid in block.span_ids})
        values.append(
            SelectedValue(
                text=text,
                kind=block.kind,
                provenance=Provenance(pages=pages, span_ids=list(block.span_ids), text=text),
            )
        )
    return FieldResult(field=field, status=selection.status, reason=selection.reason, values=values)
