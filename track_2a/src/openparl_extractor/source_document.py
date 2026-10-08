import re
from collections.abc import Sequence
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SPAN_ID_PATTERN = re.compile(r"^p(\d{3,})-b(\d{3,})-s(\d{3,})$")
LINE_SEPARATOR = "\n"
BLOCK_SEPARATOR = "\n\n"
PAGE_SEPARATOR = "\n\n"

SpanSource = Literal["native_text", "ocr", "api_text"]
WarningCode = Literal["empty_page", "no_text_layer"]


class SourceDocumentError(ValueError):
    pass


def span_id(page: int, block: int, span: int) -> str:
    return f"p{page:03d}-b{block:03d}-s{span:03d}"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Span(Strict):
    id: str
    page: int = Field(ge=1)
    text: str
    bbox: tuple[float, float, float, float] | None = None
    source: SpanSource = "native_text"


class Block(Strict):
    id: str
    spans: tuple[Span, ...]


class Page(Strict):
    number: int = Field(ge=1)
    blocks: tuple[Block, ...]


class ReadabilityWarning(Strict):
    page: int = Field(ge=1)
    code: WarningCode
    message: str


class SourceDocument(Strict):
    document_id: int
    affair_id: int | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_method: str
    pages: tuple[Page, ...]
    warnings: tuple[ReadabilityWarning, ...] = ()

    @model_validator(mode="after")
    def check_structure(self) -> Self:
        seen: set[str] = set()
        for index, page in enumerate(self.pages, start=1):
            if page.number != index:
                raise ValueError(f"Page {page.number} out of order, expected {index}")
            for block in page.blocks:
                for span in block.spans:
                    self._check_span(span, page, block, seen)
        self._check_warnings()
        return self

    def _check_span(self, span: Span, page: Page, block: Block, seen: set[str]) -> None:
        match = SPAN_ID_PATTERN.match(span.id)
        if not match or int(match[1]) != page.number or span.page != page.number:
            raise ValueError(f"Span {span.id} inconsistent with page {page.number}")
        if not block.id or not span.id.startswith(f"{block.id}-s"):
            raise ValueError(f"Span {span.id} not in block {block.id}")
        if span.id in seen:
            raise ValueError(f"Duplicate span id {span.id}")
        seen.add(span.id)

    def _check_warnings(self) -> None:
        pages_with_spans = {p.number for p in self.pages if any(b.spans for b in p.blocks)}
        flagged = {w.page for w in self.warnings}
        for page in self.pages:
            if page.number not in pages_with_spans and page.number not in flagged:
                raise ValueError(f"Page {page.number} has neither spans nor a warning")

    def spans_by_id(self) -> dict[str, tuple[Span, Block]]:
        return {span.id: (span, block) for page in self.pages for block in page.blocks for span in block.spans}


def reconstruct_text(document: SourceDocument, span_ids: Sequence[str]) -> str:
    """Derive original text from an ordered span id list; spans in the same block
    are joined by a newline, block or page changes by a blank line."""
    if not span_ids:
        raise SourceDocumentError("No span ids given")
    index = {sid: position for position, sid in enumerate(document.spans_by_id())}
    lookup = document.spans_by_id()
    missing = [sid for sid in span_ids if sid not in lookup]
    if missing:
        raise SourceDocumentError(f"Unknown span ids: {', '.join(missing)}")
    positions = [index[sid] for sid in span_ids]
    if any(later <= earlier for earlier, later in zip(positions, positions[1:])):
        raise SourceDocumentError("Span ids not in strictly ascending document order")
    return _join(lookup, span_ids)


def _join(lookup: dict[str, tuple[Span, Block]], span_ids: Sequence[str]) -> str:
    parts: list[str] = []
    previous: tuple[Span, Block] | None = None
    for sid in span_ids:
        span, block = lookup[sid]
        if previous is not None:
            parts.append(_separator(previous, (span, block)))
        parts.append(span.text)
        previous = (span, block)
    return "".join(parts)


def _separator(previous: tuple[Span, Block], current: tuple[Span, Block]) -> str:
    if previous[0].page != current[0].page:
        return PAGE_SEPARATOR
    if previous[1].id != current[1].id:
        return BLOCK_SEPARATOR
    return LINE_SEPARATOR
