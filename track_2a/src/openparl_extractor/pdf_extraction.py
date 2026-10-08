import hashlib
from pathlib import Path

import pymupdf

from openparl_extractor.source_document import (
    Block,
    Page,
    ReadabilityWarning,
    SourceDocument,
    Span,
    span_id,
)

PDF_SIGNATURE = b"%PDF-"
EXTRACTION_METHOD = f"pymupdf-{pymupdf.VersionBind}-dict-sort-lines"
TEXT_BLOCK = 0


class NotAPdfError(ValueError):
    pass


def extract_source_document(path: Path, document_id: int, affair_id: int | None = None) -> SourceDocument:
    data = path.read_bytes()
    if not data.startswith(PDF_SIGNATURE):
        raise NotAPdfError(f"{path} lacks %PDF- signature")
    pages: list[Page] = []
    warnings: list[ReadabilityWarning] = []
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for number, pdf_page in enumerate(pdf, start=1):
            page = _extract_page(pdf_page, number)
            pages.append(page)
            warnings.extend(_page_warnings(pdf_page, page))
    return SourceDocument(
        document_id=document_id,
        affair_id=affair_id,
        sha256=hashlib.sha256(data).hexdigest(),
        extraction_method=EXTRACTION_METHOD,
        pages=tuple(pages),
        warnings=tuple(warnings),
    )


def _extract_page(pdf_page: pymupdf.Page, number: int) -> Page:
    raw_blocks = pdf_page.get_text("dict", sort=True)["blocks"]
    blocks: list[Block] = []
    for raw in (b for b in raw_blocks if b["type"] == TEXT_BLOCK):
        block = _build_block(raw, number, len(blocks) + 1)
        if block.spans:
            blocks.append(block)
    return Page(number=number, blocks=tuple(blocks))


def _build_block(raw: dict, page: int, block_number: int) -> Block:
    block_id = f"p{page:03d}-b{block_number:03d}"
    spans = []
    for line in raw["lines"]:
        text = "".join(piece["text"] for piece in line["spans"])
        if text.strip():
            spans.append(
                Span(
                    id=span_id(page, block_number, len(spans) + 1),
                    page=page,
                    text=text,
                    bbox=tuple(line["bbox"]),
                )
            )
    return Block(id=block_id, spans=tuple(spans))


def _page_warnings(pdf_page: pymupdf.Page, page: Page) -> list[ReadabilityWarning]:
    if any(block.spans for block in page.blocks):
        return []
    if pdf_page.get_images():
        return [ReadabilityWarning(page=page.number, code="no_text_layer", message="Image-only page, OCR needed")]
    return [ReadabilityWarning(page=page.number, code="empty_page", message="Page has no text")]
