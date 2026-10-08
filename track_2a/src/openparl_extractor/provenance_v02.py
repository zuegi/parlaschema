from collections.abc import Mapping

from openparl_extractor.provenance import source_pages, validate_evidence
from openparl_extractor.schema import iter_evidence
from openparl_extractor.schema_v02 import DocumentExtraction


def validate_provenance(
    extraction: DocumentExtraction, documents: Mapping[int, tuple[str, ...]]
) -> None:
    source_pages(extraction.document_id, documents)
    for source in iter_evidence(extraction):
        validate_evidence(source, documents)
