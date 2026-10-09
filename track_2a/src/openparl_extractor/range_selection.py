import json
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from openparl_extractor.source_document import SourceDocument, SourceDocumentError
from openparl_extractor.span_selection import (
    FieldName,
    Kind,
    Provenance,
    SelectedValue,
    SelectionError,
    derive_text,
)

PROCEDURE_VERSION = "range-v1"
RangeStatus = Literal["known", "partial", "not_found"]
MAX_TOKENS: dict[FieldName, int] = {"title": 300, "submitters": 600, "question_or_request": 2048}
TITLE_REVIEW_MAX_LINES = 3
TITLE_REVIEW_MAX_CHARS = 300

SYSTEM_PROMPT = (
    "You receive the text of a Swiss parliamentary document as lines, each prefixed with a local id "
    "like [L12]. Page boundaries are marked '=== PAGE n ==='. Select text only by id ranges; never "
    "output document text. Output exactly one line of compact JSON: no indentation, no newlines, no "
    "other text. Form: {\"status\":\"known\",\"ranges\":[{\"first\":\"L3\",\"last\":\"L5\"}]}. "
    "A range is closed: first and last are ids shown in the input, first not after last, and it "
    "covers every line from first to last. Ranges are in document order and do not overlap. "
    "Status 'known': everything requested found. 'partial': only part found. 'not_found': nothing "
    "found, with an empty ranges array. Do not infer anything that is not stated in the text."
)
FIELD_PROMPTS: dict[FieldName, str] = {
    "title": (
        "Select the short heading that names the affair. Exclude the question body, justification "
        "and submitter names. Choose the smallest complete range (typically 1 to 3 lines) and "
        "return exactly one range. Use only the text of this PDF."
    ),
    "submitters": (
        "Select the lines naming the persons who submitted the affair, one range per submitter or "
        "contiguous group of lines. Exclude executive signatories and the answering government or "
        "council. Do not include unnamed co-signatories; use 'partial' if the text indicates "
        "further unnamed submitters."
    ),
    "question_or_request": (
        "Select every independent numbered question or request put by the submitters, one range "
        "per item. List sub-questions (1a, 1b, ...) as separate ranges and never merge numbered "
        "items. Each range has a 'kind': 'question', 'request' or null if not unambiguous. Do not "
        "select answers. Form: {\"status\":\"known\",\"ranges\":[{\"first\":\"L3\",\"last\":\"L5\","
        "\"kind\":\"question\"}]}."
    ),
}


class Range(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first: str
    last: str
    kind: Kind | None = None


class RangeSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: RangeStatus
    ranges: list[Range]

    @model_validator(mode="after")
    def check_status_consistency(self) -> "RangeSelection":
        if self.status == "not_found" and self.ranges:
            raise ValueError("not_found must have no ranges")
        if self.status != "not_found" and not self.ranges:
            raise ValueError(f"{self.status} needs at least one range")
        return self


class RangeFieldResult(BaseModel):
    field: FieldName
    status: RangeStatus
    values: list[SelectedValue]
    needs_review: list[str]


def local_id_map(document: SourceDocument) -> dict[str, str]:
    return {f"L{position}": sid for position, sid in enumerate(document.spans_by_id(), start=1)}


def render_local_lines(document: SourceDocument) -> str:
    to_local = {sid: local for local, sid in local_id_map(document).items()}
    lines: list[str] = []
    for page in document.pages:
        lines.append(f"=== PAGE {page.number} ===")
        for block in page.blocks:
            lines.extend(f"[{to_local[span.id]}] {span.text.rstrip()}" for span in block.spans)
    return "\n".join(lines)


def response_schema(field: FieldName, local_ids: Sequence[str]) -> dict[str, Any]:
    id_schema = {"type": "string", "enum": list(local_ids)}
    item: dict[str, Any] = {
        "type": "object",
        "properties": {"first": id_schema, "last": id_schema},
        "required": ["first", "last"],
        "additionalProperties": False,
    }
    if field == "question_or_request":
        item["properties"]["kind"] = {"type": ["string", "null"], "enum": ["question", "request", None]}
        item["required"].append("kind")
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["known", "partial", "not_found"]},
            "ranges": {"type": "array", "items": item},
        },
        "required": ["status", "ranges"],
        "additionalProperties": False,
    }


def build_request_body(model: str, field: FieldName, document: SourceDocument) -> dict[str, Any]:
    local_ids = list(local_id_map(document))
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Field: {field}\n{FIELD_PROMPTS[field]}\n\n{render_local_lines(document)}"},
        ],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": MAX_TOKENS[field],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": f"{field}_ranges",
                "strict": True,
                "schema": response_schema(field, local_ids),
            },
        },
    }


def parse_json_object(content: str) -> Any:
    """Accept one complete JSON value followed by whitespace only; nothing else is repaired."""
    text = content.lstrip()
    try:
        value, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as error:
        raise SelectionError(f"Invalid or truncated JSON: {error}") from error
    if text[end:].strip():
        raise SelectionError("Extra content after JSON object")
    return value


def parse_range_selection(field: FieldName, content: str) -> RangeSelection:
    try:
        selection = RangeSelection.model_validate(parse_json_object(content))
    except ValidationError as error:
        raise SelectionError(f"Invalid selection output: {error}") from error
    if field != "question_or_request" and any(r.kind for r in selection.ranges):
        raise SelectionError(f"kind not allowed for {field}")
    if field == "title" and len(selection.ranges) > 1:
        raise SelectionError("title must be a single range")
    return selection


def expand_ranges(document: SourceDocument, selection: RangeSelection) -> list[list[str]]:
    local = local_id_map(document)
    stable = list(local.values())
    position = {sid: index for index, sid in enumerate(stable)}
    expanded: list[list[str]] = []
    previous_end = -1
    for item in selection.ranges:
        if item.first not in local or item.last not in local:
            raise SelectionError(f"Unknown local id in range {item.first}-{item.last}")
        start, end = position[local[item.first]], position[local[item.last]]
        if start > end:
            raise SelectionError(f"Reversed range {item.first}-{item.last}")
        if start <= previous_end:
            raise SelectionError(f"Range {item.first}-{item.last} overlaps or precedes previous range")
        previous_end = end
        expanded.append(stable[start : end + 1])
    return expanded


def title_review_reasons(text: str, line_count: int) -> list[str]:
    reasons = []
    if line_count > TITLE_REVIEW_MAX_LINES:
        reasons.append(f"title spans {line_count} lines")
    if len(text) > TITLE_REVIEW_MAX_CHARS:
        reasons.append(f"title has {len(text)} characters")
    return reasons


def build_range_result(document: SourceDocument, field: FieldName, selection: RangeSelection) -> RangeFieldResult:
    lookup = document.spans_by_id()
    values: list[SelectedValue] = []
    review: list[str] = []
    for item, span_ids in zip(selection.ranges, expand_ranges(document, selection)):
        try:
            text = derive_text(document, field, span_ids)
        except SourceDocumentError as error:
            raise SelectionError(str(error)) from error
        pages = sorted({lookup[sid][0].page for sid in span_ids})
        provenance = Provenance(pages=pages, span_ids=span_ids, text=text)
        values.append(SelectedValue(text=text, kind=item.kind, provenance=provenance))
        if field == "title":
            review.extend(title_review_reasons(text, len(span_ids)))
    return RangeFieldResult(field=field, status=selection.status, values=values, needs_review=review)
