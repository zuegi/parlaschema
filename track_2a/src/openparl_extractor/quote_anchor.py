import json
import re
from dataclasses import dataclass

from pydantic import Field

from openparl_extractor.source_document import (
    BLOCK_SEPARATOR, LINE_SEPARATOR, PAGE_SEPARATOR, SourceDocument, Strict,
)


class AnchorError(ValueError):
    pass


class Anchor(Strict):
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)


class Selection(Strict):
    blocks: tuple[Anchor, ...]


@dataclass(frozen=True)
class Stream:
    original: str
    search: str
    mapping: tuple[tuple[int, int], ...]
    spans: tuple[dict, ...]
    pages: tuple[dict, ...]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def search_mapping(text: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    characters, positions = [], []
    for match in re.finditer(r"\s+|[^\s]", text):
        characters.append(" " if match[0].isspace() else match[0])
        positions.append((match.start(), match.end()))
    left = 1 if characters and characters[0] == " " else 0
    right = len(characters) - (1 if characters and characters[-1] == " " else 0)
    return "".join(characters[left:right]), tuple(positions[left:right])


def build_stream(document: SourceDocument) -> Stream:
    parts, spans, pages = [], [], []
    offset, previous = 0, None
    for page in document.pages:
        page_parts = []
        for block in page.blocks:
            for span in block.spans:
                separator = _separator(previous, span.page, block.id)
                parts.extend((separator, span.text))
                page_parts.extend(("" if previous is None or previous[0] != span.page else separator, span.text))
                offset += len(separator)
                spans.append({"id": span.id, "page": span.page, "start": offset, "end": offset + len(span.text)})
                offset += len(span.text)
                previous = (span.page, block.id)
        pages.append({"page": page.number, "text": normalize("".join(page_parts))})
    original = "".join(parts)
    search, mapping = search_mapping(original)
    return Stream(original, search, mapping, tuple(spans), tuple(pages))


def _separator(previous: tuple | None, page: int, block: str) -> str:
    if previous is None:
        return ""
    if previous[0] != page:
        return PAGE_SEPARATOR
    return BLOCK_SEPARATOR if previous[1] != block else LINE_SEPARATOR


def parse_selection(content: str) -> Selection:
    return Selection.model_validate(_strict_json(content))


def _strict_json(content: str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AnchorError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(content, object_pairs_hook=pairs)


def _unique_position(search: str, anchor: str) -> int:
    needle = normalize(anchor)
    if not needle:
        raise AnchorError("Empty normalized anchor")
    positions = [m.start() for m in re.finditer(f"(?={re.escape(needle)})", search)]
    if len(positions) != 1:
        raise AnchorError(f"Anchor matches: {len(positions)}; missing or ambiguous")
    return positions[0]


def resolve(stream: Stream, selection: Selection) -> list[dict]:
    result, previous_end = [], 0
    for anchor in selection.blocks:
        start = _unique_position(stream.search, anchor.start)
        end_start = _unique_position(stream.search, anchor.end)
        end = end_start + len(normalize(anchor.end))
        if end_start < start or end < start + len(normalize(anchor.start)) or start < previous_end:
            raise AnchorError("Reversed, empty, overlapping or unordered main blocks")
        result.append(_passage(stream, start, end))
        previous_end = end
    return result


def _passage(stream: Stream, start: int, end: int) -> dict:
    left, right = stream.mapping[start][0], stream.mapping[end - 1][1]
    spans = [
        {**span, "local_start": max(left, span["start"]) - span["start"],
         "local_end": min(right, span["end"]) - span["start"]}
        for span in stream.spans if span["start"] < right and span["end"] > left
    ]
    return {
        "search_start": start, "search_end": end,
        "source_start": left, "source_end": right,
        "text": stream.original[left:right], "spans": spans,
        "pages": list(dict.fromkeys(span["page"] for span in spans)),
    }
