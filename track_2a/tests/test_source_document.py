from pathlib import Path

import pymupdf
import pytest

from openparl_extractor.pdf_extraction import NotAPdfError, extract_source_document
from openparl_extractor.source_document import SourceDocument, SourceDocumentError, reconstruct_text


def make_pdf(path: Path, pages: list[list[str]]) -> Path:
    pdf = pymupdf.open()
    for blocks in pages:
        page = pdf.new_page()
        y = 72
        for text in blocks:
            page.insert_text((72, y), text, fontsize=11)
            y += 60
    pdf.save(path)
    return path


@pytest.fixture
def pdf_path(tmp_path):
    return make_pdf(
        tmp_path / "a.pdf",
        [["Interpellazione n. 1", "Domanda: perché?"], [], ["Risposta del Consiglio"]],
    )


@pytest.fixture
def document(pdf_path):
    return extract_source_document(pdf_path, document_id=7, affair_id=3)


def all_ids(document):
    return list(document.spans_by_id())


def test_span_ids_are_stable(pdf_path):
    first = extract_source_document(pdf_path, 7)
    second = extract_source_document(pdf_path, 7)
    assert all_ids(first) == all_ids(second)
    assert first.model_dump() == second.model_dump()
    assert all_ids(first)[0] == "p001-b001-s001"


def test_structure_and_pages_not_merged(document):
    assert [page.number for page in document.pages] == [1, 2, 3]
    assert all(span.page == 1 for span in (s for s, _ in document.spans_by_id().values()) if span.id.startswith("p001"))
    assert document.pages[2].blocks[0].spans[0].text == "Risposta del Consiglio"


def test_empty_page_warns(document):
    assert [(w.page, w.code) for w in document.warnings] == [(2, "empty_page")]
    assert document.pages[1].blocks == ()


def test_exact_reconstruction(document):
    ids = all_ids(document)
    assert reconstruct_text(document, ids[:1]) == "Interpellazione n. 1"
    assert reconstruct_text(document, ids[:2]) == "Interpellazione n. 1\n\nDomanda: perché?"


def test_multi_page_reconstruction(document):
    ids = all_ids(document)
    text = reconstruct_text(document, [ids[1], ids[2]])
    assert text == "Domanda: perché?\n\nRisposta del Consiglio"


def test_unknown_id_rejected(document):
    with pytest.raises(SourceDocumentError, match="Unknown"):
        reconstruct_text(document, ["p009-b001-s001"])


def test_wrong_order_and_duplicates_rejected(document):
    ids = all_ids(document)
    with pytest.raises(SourceDocumentError, match="order"):
        reconstruct_text(document, [ids[1], ids[0]])
    with pytest.raises(SourceDocumentError, match="order"):
        reconstruct_text(document, [ids[0], ids[0]])


def test_empty_selection_rejected(document):
    with pytest.raises(SourceDocumentError):
        reconstruct_text(document, [])


def test_page_without_spans_or_warning_rejected(document):
    data = document.model_dump()
    data["warnings"] = []
    with pytest.raises(ValueError, match="neither spans nor a warning"):
        SourceDocument.model_validate(data)


def test_duplicate_span_id_rejected(document):
    data = document.model_dump()
    data["pages"][0]["blocks"][1]["spans"][0]["id"] = "p001-b001-s001"
    with pytest.raises(ValueError):
        SourceDocument.model_validate(data)


def test_json_roundtrip(document):
    assert SourceDocument.model_validate_json(document.model_dump_json()) == document


def test_non_pdf_rejected(tmp_path):
    fake = tmp_path / "x.pdf"
    fake.write_bytes(b"<html>")
    with pytest.raises(NotAPdfError):
        extract_source_document(fake, 1)
