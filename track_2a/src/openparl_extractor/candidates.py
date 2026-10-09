"""Deterministic candidate generation with exact character offsets into SourceDocument spans.

Candidates are possibilities, never decisions. Rules are language-agnostic keyword/layout
rules for de/fr/it; there are no document-specific cases and no reference input.
"""

import re
from bisect import bisect_right
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, ConfigDict

from openparl_extractor.source_document import (
    BLOCK_SEPARATOR,
    LINE_SEPARATOR,
    PAGE_SEPARATOR,
    SourceDocument,
    SourceDocumentError,
    Span,
)

GENERATOR_VERSION = "candidates-v2"
CandidateField = Literal["title", "submitters", "question_or_request"]
CandidateKind = Literal["heading", "name_only", "context", "main_item", "subitem"]
CANDIDATE_FIELDS: tuple[CandidateField, ...] = ("title", "submitters", "question_or_request")
MAX_HEADING_LINES = 3
MAX_HEADING_CHARACTERS = 300
MIN_HEADING_WORDS = 4
EARLY_PAGE_FRACTION = 0.4
MIN_ISOLATION_HEIGHTS = 0.5
SECTION_HEADING = re.compile(
    r"(?i)^\s*(?:begründung|motivation|motivazione|giustificazione|rappel|réponse|risposta|antwort|"
    r"si chiede|domande|fragen)\b"
)

INSTRUMENT = (
    r"(?i:interpellation|interpellanza|postulat|postulato|motion|mozione|anfrage|"
    r"interrogazione|question|initiative|iniziativa|petition|petizione)"
)
TITLE_LABEL = re.compile(r"(?im)^[ \t]*(?:betreffend|betrifft|concernant|objet|oggetto|gegenstand)\b[ \t:]*")
SKIPPED_AFTER_HEADING = re.compile(
    r"(?i)^\s*(?:betreffend|betrifft|concernant|objet|oggetto|presentat[ao] da|eingereicht|von\b|par\b|data|datum|date|"
    r"numero|nummer|kr-nr)"
)
PERSON = r"[A-ZÀ-ÖØ-Þ][^\W\d_]*(?:[-'’][^\W\d_]+)*"
PARTICLE = r"(?:(?:de|di|da|del|della|von|van|der|den|dos|du|la|le)[ \t]+|d['’])"
NAME = rf"{PERSON}(?:[ \t]+(?:{PARTICLE})?{PERSON}){{1,3}}"
GROUP_MARKER = r"(?:[ \t]+(?i:et consorts|e cofirmatari|und mitunterzeichnende[rn]?|und mitunterzeichner))"
SUBMITTER_LABEL = re.compile(
    r"(?im)^[ \t]*(?:von|par|da|presentat[ao] da:?|eingereicht von:?|interpellant(?:in)?:?|einreicher(?:in)?:?|"
    r"firmatari[oa]:?|auteure?:?|déposante?:?)[ \t]+(?-i:(?P<name>" + NAME + "))"
)
OFFICE = (
    r"(?:Kantonsrät(?:in)?|Kantonsrat|Gemeinderät(?:in)?|Gemeinderat|Nationalrät(?:in)?|Nationalrat|Ständerät(?:in)?|"
    r"Ständerat|Grossrät(?:in)?|Grossrat|Député(?:e)?|Conseill(?:er|ère)(?:[ \t]+(?:national|communal)(?:e)?)?|"
    r"Deputat[oa]|Consigliere|Consigliera|Municipal(?:e)?)"
)
SUBMITTER_OFFICE = re.compile(rf"\b{OFFICE}[ \t]+(?P<name>{NAME})")
SUBMITTER_INSTRUMENT = re.compile(rf"{INSTRUMENT}[ \t]+(?P<name>{NAME})(?P<group>{GROUP_MARKER})?")
NAME_CONTINUATION = re.compile(rf"[ \t]+(?:{PARTICLE})?{PERSON}")
INSTRUMENT_HEADING = re.compile(rf"^\s*{INSTRUMENT}\b")
PARENTHESIZED_TITLE = re.compile(rf"(?m)^[ \t]*\d{{1,4}}\.[ \t]+{INSTRUMENT}[ \t]*\((?P<title>.+?)\)[ \t]*$", re.DOTALL)
DASH_PREFIX = rf"{INSTRUMENT}[ \t]+{NAME}(?:{GROUP_MARKER})?[ \t]+[-–—][ \t]+"
DASH_TITLE = re.compile(DASH_PREFIX + r"(?P<title>.{3,400}?)(?=\n\n|\Z)", re.DOTALL)
DASH_TITLE_WITH_REFERENCE = re.compile(
    DASH_PREFIX + r"(?P<title>.{3,400}?)[ \t\n]*\([^()\n]*\d[^()\n]*\)[ \t]*(?=\n|\Z)", re.DOTALL
)
ITEM_MARKER = re.compile(r"(?m)^[ \t\u2007\u2002]*(?P<number>\d{1,2})[ \t]?[.)](?=[\s])[ \t\x07\u2007]*")
SUBITEM_MARKER = re.compile(r"(?m)^[ \t]*(?P<letter>[a-z])[.)](?=[\s])[ \t\x07]*")
ANSWER_BOUNDARY = re.compile(
    r"(?m)^[ \t]*(?:Réponse\b|Risposta\b|Antwort\b|Auf Antrag\b|b e s c h l i e s s t|beschliesst\b|Zu Frage\b|Zur Frage\b)"
)
SENTENCE_END = ("?", ".", "!", ":", ")", "»")
PAGE_NUMBER_LINE = re.compile(r"^[\W\d]*(?:di|von|de|of|/)?[\W\d]*$")


class Anchor(BaseModel):
    model_config = ConfigDict(frozen=True)
    span_id: str
    offset: int


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    field: CandidateField
    kind: CandidateKind
    role: Literal["potential_submitter"] | None = None
    rule: str
    start: Anchor
    end: Anchor
    text: str
    span_ids: tuple[str, ...]
    pages: tuple[int, ...]
    notes: tuple[str, ...] = ()


class CandidateSet(BaseModel):
    document_id: int
    generator_version: str = GENERATOR_VERSION
    candidates: tuple[Candidate, ...]
    missing: dict[str, str]
    needs_review: dict[str, str]


class Stream:
    """Whole-document text built from unchanged span texts; index <-> (span, offset)."""

    def __init__(self, document: SourceDocument):
        self.spans: list[tuple[int, Span, str]] = []
        parts: list[str] = []
        position = 0
        previous: tuple[Span, str] | None = None
        for page in document.pages:
            for block in page.blocks:
                for span in block.spans:
                    if previous is not None:
                        separator = _separator(previous, (span, block.id))
                        parts.append(separator)
                        position += len(separator)
                    self.spans.append((position, span, block.id))
                    parts.append(span.text)
                    position += len(span.text)
                    previous = (span, block.id)
        self.text = "".join(parts)
        self._starts = [start for start, _, _ in self.spans]
        self._by_id = {span.id: start for start, span, _ in self.spans}

    def index(self, anchor: Anchor) -> int:
        try:
            return self._by_id[anchor.span_id] + anchor.offset
        except KeyError as error:
            raise SourceDocumentError(f"Unknown span id {anchor.span_id}") from error

    def anchors(self, start: int, end: int) -> tuple[Anchor, Anchor]:
        first = self._locate(start)
        last = self._locate(end - 1)
        return Anchor(span_id=first[1].id, offset=start - first[0]), Anchor(
            span_id=last[1].id, offset=end - last[0]
        )

    def _locate(self, index: int) -> tuple[int, Span, str]:
        entry = self.spans[bisect_right(self._starts, index) - 1]
        if not 0 <= index - entry[0] < len(entry[1].text):
            raise SourceDocumentError(f"Index {index} lies outside any span")
        return entry

    def covered(self, start: int, end: int) -> list[tuple[int, Span, str]]:
        return [e for e in self.spans if e[0] < end and e[0] + len(e[1].text) > start]


def _separator(previous: tuple[Span, str], current: tuple[Span, str]) -> str:
    if previous[0].page != current[0].page:
        return PAGE_SEPARATOR
    return LINE_SEPARATOR if previous[1] == current[1] else BLOCK_SEPARATOR


def slice_text(document: SourceDocument, start: Anchor, end: Anchor) -> str:
    """Exact text between two offset anchors; rejects unknown spans, bad offsets and reversed order."""
    stream = Stream(document)
    lengths = {span.id: len(span.text) for _, span, _ in stream.spans}
    for anchor in (start, end):
        if anchor.span_id not in lengths or not 0 <= anchor.offset <= lengths[anchor.span_id]:
            raise SourceDocumentError(f"Invalid anchor {anchor.span_id}:{anchor.offset}")
    first, last = stream.index(start), stream.index(end)
    if first >= last:
        raise SourceDocumentError("Anchors empty or in reverse order")
    return stream.text[first:last]


def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


class _Builder:
    def __init__(self, document: SourceDocument):
        self.stream = Stream(document)
        self.counter = 0
        self.items: list[Candidate] = []
        self._seen: set[tuple[str, int, int]] = set()

    def add(
        self, field: CandidateField, rule: str, start: int, end: int,
        notes: tuple[str, ...] = (), kind: CandidateKind | None = None,
    ) -> None:
        start, end = _trimmed(self.stream.text, start, end)
        if start >= end or (field, start, end) in self._seen:
            return
        self._seen.add((field, start, end))
        first, last = self.stream.anchors(start, end)
        covered = self.stream.covered(start, end)
        self.counter += 1
        self.items.append(
            Candidate(
                id=f"{field}-{self.counter:03d}",
                field=field,
                kind=kind or _candidate_kind(field, notes),
                role="potential_submitter" if field == "submitters" else None,
                rule=rule,
                start=first,
                end=last,
                text=self.stream.text[start:end],
                span_ids=tuple(span.id for _, span, _ in covered),
                pages=tuple(sorted({span.page for _, span, _ in covered})),
                notes=notes,
            )
        )


def _candidate_kind(field: CandidateField, notes: tuple[str, ...]) -> CandidateKind:
    if field == "title":
        return "heading"
    if field == "submitters":
        return "name_only"
    return "subitem" if "subpart" in notes else "main_item"


def _block_bounds(stream: Stream) -> list[tuple[int, int, str]]:
    bounds: list[tuple[int, int, str]] = []
    for start, span, block_id in stream.spans:
        end = start + len(span.text)
        if bounds and bounds[-1][2] == block_id and bounds[-1][1] <= start:
            bounds[-1] = (bounds[-1][0], end, block_id)
        else:
            bounds.append((start, end, block_id))
    return bounds


def _normalized(text: str) -> str:
    return " ".join(text.split()).lower()


def _furniture_texts(stream: Stream, bounds: list[tuple[int, int, str]]) -> set[str]:
    pages_by_text: dict[str, set[int]] = {}
    for start, end, _ in bounds:
        page = stream.spans[bisect_right(stream._starts, start) - 1][1].page
        pages_by_text.setdefault(_normalized(stream.text[start:end]), set()).add(page)
    return {text for text, pages in pages_by_text.items() if len(pages) > 1}


def _is_furniture(text: str, furniture: set[str]) -> bool:
    return _normalized(text) in furniture or bool(PAGE_NUMBER_LINE.match(text.strip()))


def _letter_spaced(text: str) -> str:
    tokens = text.split()
    if len(tokens) > 2 and sum(len(t) == 1 for t in tokens) >= 0.6 * len(tokens):
        return "".join(tokens)
    return text


def _title_candidates(builder: _Builder, bounds: list[tuple[int, int, str]], furniture: set[str]) -> None:
    text = builder.stream.text
    for match in TITLE_LABEL.finditer(text):
        position = match.end()
        index = next((i for i, b in enumerate(bounds) if b[0] <= position <= b[1]), None)
        if index is None:
            continue
        if not text[position : bounds[index][1]].strip() and index + 1 < len(bounds):
            index, position = index + 1, bounds[index + 1][0]
        builder.add("title", "title.label-to-block-end", position, bounds[index][1])
    for match in PARENTHESIZED_TITLE.finditer(text):
        builder.add("title", "title.parenthesized-after-instrument", match.start("title"), match.end("title"))
    for rule, pattern in (
        ("title.dash-after-instrument", DASH_TITLE),
        ("title.dash-until-reference", DASH_TITLE_WITH_REFERENCE),
    ):
        for match in pattern.finditer(text):
            builder.add("title", rule, match.start("title"), match.end("title"))
    for index, (start, end, _) in enumerate(bounds[:-1]):
        heading = text[start:end]
        following = text[bounds[index + 1][0] : bounds[index + 1][1]]
        if _is_furniture(heading, furniture) or not INSTRUMENT_HEADING.match(_letter_spaced(heading.split("\n")[0])):
            continue
        if not SKIPPED_AFTER_HEADING.match(following) and not _is_furniture(following, furniture):
            builder.add("title", "title.block-after-instrument-heading", bounds[index + 1][0], bounds[index + 1][1])


def _heading_like(text: str, line_count: int, furniture: set[str]) -> bool:
    return (
        line_count <= MAX_HEADING_LINES
        and len(text.strip()) <= MAX_HEADING_CHARACTERS
        and len(text.split()) >= MIN_HEADING_WORDS
        and not text.rstrip().endswith((".", ":", ";"))
        and not _is_furniture(text, furniture)
        and not SKIPPED_AFTER_HEADING.match(text)
        and not INSTRUMENT_HEADING.match(_letter_spaced(text.split("\n")[0]))
        and not ITEM_MARKER.match(text)
        and not SUBMITTER_OFFICE.search(text)
    )


def _layout_titles(builder: _Builder, bounds: list[tuple[int, int, str]], furniture: set[str]) -> None:
    entries = [(start, span, block) for start, span, block in builder.stream.spans if span.page == 1]
    boxes = [span.bbox for _, span, _ in entries if span.bbox is not None]
    if not boxes:
        return
    top, bottom = min(box[1] for box in boxes), max(box[3] for box in boxes)
    cutoff = top + EARLY_PAGE_FRACTION * (bottom - top)
    for start, end, _ in bounds:
        covered = builder.stream.covered(start, end)
        if not covered or covered[0][1].page != 1:
            break
        text = builder.stream.text[start:end]
        if SECTION_HEADING.match(text):
            break
        if _heading_like(text, len(covered), furniture) and _isolated_heading(covered, entries, cutoff):
            builder.add("title", "title.early-isolated-layout", start, end, ("heuristic", "needs_review"))


def _isolated_heading(
    covered: list[tuple[int, Span, str]], entries: list[tuple[int, Span, str]], cutoff: float,
) -> bool:
    boxes = [span.bbox for _, span, _ in covered if span.bbox is not None]
    if len(boxes) != len(covered) or max(box[3] for box in boxes) > cutoff:
        return False
    top, bottom = min(box[1] for box in boxes), max(box[3] for box in boxes)
    height = max(box[3] - box[1] for box in boxes)
    others = [span.bbox for _, span, block in entries if block != covered[0][2] and span.bbox is not None]
    above = [top - box[3] for box in others if box[3] <= top]
    below = [box[1] - bottom for box in others if box[1] >= bottom]
    return bool(above and below and min(above + below) >= MIN_ISOLATION_HEIGHTS * height)


def _submitter_candidates(builder: _Builder) -> None:
    text = builder.stream.text
    for rule, pattern in (
        ("submitters.label-name", SUBMITTER_LABEL),
        ("submitters.office-name", SUBMITTER_OFFICE),
        ("submitters.instrument-name", SUBMITTER_INSTRUMENT),
    ):
        for match in pattern.finditer(text):
            notes = ("unnamed_group_marker",) if "group" in pattern.groupindex and match.group("group") else ()
            if not NAME_CONTINUATION.match(text, match.end("name")):
                builder.add("submitters", rule, match.start("name"), match.end("name"), notes)
            covered = builder.stream.covered(match.start("name"), match.end("name"))
            start, _, _ = covered[0]
            last, final_span, _ = covered[-1]
            builder.add(
                "submitters", rule.replace("-name", "-context"), start, last + len(final_span.text),
                notes + ("context_not_role_confirmation",), kind="context",
            )


def _continues(previous_text: str) -> bool:
    return not previous_text.rstrip().endswith(SENTENCE_END)


def _item_end(builder: _Builder, bounds: list[tuple[int, int, str]], furniture: set[str], start: int, limit: int) -> int:
    text = builder.stream.text
    end = start
    for b_start, b_end, _ in bounds:
        if b_end <= start:
            continue
        if b_start >= limit:
            break
        block_text = text[b_start:b_end]
        if end > start and not SUBITEM_MARKER.match(block_text) and not _continues(text[start:end]):
            break
        if end > start and _is_furniture(block_text, furniture):
            continue
        end = min(b_end, limit)
    return end


def _numbered_chain(markers: list[re.Match[str]], boundary: int) -> list[re.Match[str]]:
    before = [m for m in markers if m.start() < boundary]
    best: list[re.Match[str]] = []
    for first in (m for m in before if m.group("number") == "1"):
        chain = [first]
        for match in before:
            if match.start() > chain[-1].start() and int(match.group("number")) == len(chain) + 1:
                chain.append(match)
        if len(chain) > len(best):
            best = chain
    return best


def _question_candidates(builder: _Builder, bounds: list[tuple[int, int, str]], furniture: set[str]) -> str | None:
    text = builder.stream.text
    boundary_match = ANSWER_BOUNDARY.search(text)
    boundary = boundary_match.start() if boundary_match else len(text)
    chain = _numbered_chain(list(ITEM_MARKER.finditer(text)), boundary)
    if not chain:
        return "no numbered question sequence starting at 1 before an answer section"
    limits = [m.start() for m in chain[1:]] + [boundary]
    for marker, limit in zip(chain, limits):
        end = _item_end(builder, bounds, furniture, marker.start(), limit)
        builder.add("question_or_request", "question.numbered-item", marker.end(), end)
        _subitem_candidates(builder, marker.end(), end)
    return None


def _subitem_candidates(builder: _Builder, start: int, end: int) -> None:
    text = builder.stream.text
    subs = [m for m in SUBITEM_MARKER.finditer(text, start, end)]
    expected = [m for index, m in enumerate(subs) if m.group("letter") == chr(ord("a") + index)]
    limits = [m.start() for m in expected[1:]] + [end]
    for marker, limit in zip(expected, limits):
        builder.add("question_or_request", "question.numbered-subitem", marker.end(), limit, ("subpart",))


def generate_candidates(document: SourceDocument) -> CandidateSet:
    builder = _Builder(document)
    bounds = _block_bounds(builder.stream)
    furniture = _furniture_texts(builder.stream, bounds)
    _title_candidates(builder, bounds, furniture)
    _layout_titles(builder, bounds, furniture)
    _submitter_candidates(builder)
    question_problem = _question_candidates(builder, bounds, furniture)
    missing = {f: f"no {f} candidate generated" for f in CANDIDATE_FIELDS if not any(c.field == f for c in builder.items)}
    if question_problem:
        missing["question_or_request"] = question_problem
    titles = [c for c in builder.items if c.field == "title"]
    review = {}
    if len(titles) > 1:
        review["title"] = "ambiguous: multiple heading candidates; no title selected"
    elif any("heuristic" in c.notes for c in titles):
        review["title"] = "layout heuristic only; needs manual review"
    elif not titles:
        review["title"] = "no supported title candidate; layout may be absent or inconclusive"
    return CandidateSet(
        document_id=document.document_id, candidates=tuple(builder.items), missing=missing, needs_review=review,
    )


def iter_candidates(candidate_set: CandidateSet, field: CandidateField) -> Iterator[Candidate]:
    return (c for c in candidate_set.candidates if c.field == field)
