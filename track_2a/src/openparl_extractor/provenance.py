from collections.abc import Mapping

from openparl_extractor.schema import DocumentExtraction, Evidence, iter_evidence


class ProvenanceError(ValueError):
    pass


def source_pages(document_id: int, documents: Mapping[int, tuple[str, ...]]) -> tuple[str, ...]:
    pages = documents.get(document_id)
    if not pages or not any(page.strip() for page in pages):
        raise ProvenanceError(f"Missing source text for document {document_id}")
    return pages


def validate_evidence(source: Evidence, documents: Mapping[int, tuple[str, ...]]) -> None:
    pages = source_pages(source.document_id, documents)
    if source.page is None:
        text = "\f".join(pages)
    elif source.page > len(pages):
        raise ProvenanceError(f"Page {source.page} outside document {source.document_id}")
    else:
        text = pages[source.page - 1]
    if source.quote not in text:
        raise ProvenanceError(f"Quote not found in document {source.document_id}, page {source.page}")


def validate_provenance(
    extraction: DocumentExtraction, documents: Mapping[int, tuple[str, ...]]
) -> None:
    source_pages(extraction.document_id, documents)
    for source in iter_evidence(extraction):
        validate_evidence(source, documents)
