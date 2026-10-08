import pytest

from openparl_extractor.provenance import ProvenanceError
from openparl_extractor.provenance_v02 import validate_provenance
from openparl_extractor.schema import CORE_FIELDS, iter_evidence
from openparl_extractor.schema_v02 import DocumentExtraction


def source_text(extraction):
    return {100: ("\n".join(source.quote for source in iter_evidence(extraction)),)}


def test_all_claim_specific_quotes_checked(document_v02):
    validate_provenance(document_v02, source_text(document_v02))


@pytest.mark.parametrize("claim", ["text", "kind"])
def test_text_and_category_quotes_fail_independently(document_v02, claim):
    documents = source_text(document_v02)
    getattr(document_v02.question_or_request.value[0], claim).sources[0].quote = "Invented quote"
    with pytest.raises(ProvenanceError, match="Quote not found"):
        validate_provenance(document_v02, documents)


@pytest.mark.parametrize("claim", ["text", "kind"])
def test_text_and_category_pages_checked_independently(document_v02, claim):
    getattr(document_v02.question_or_request.value[0], claim).sources[0].page = 2
    with pytest.raises(ProvenanceError, match="outside document"):
        validate_provenance(document_v02, source_text(document_v02))


def test_exact_quote_does_not_prove_semantic_category(document_v02):
    document_v02.question_or_request.value[0].kind.value = "request"
    validate_provenance(document_v02, source_text(document_v02))
    assert document_v02.question_or_request.value[0].kind.value == "request"


def test_quote_occurrence_does_not_prove_original_faithfulness(document_v02):
    documents = source_text(document_v02)
    document_v02.title.value.original = "Unsupported paraphrase"
    validate_provenance(document_v02, documents)


def test_no_whitespace_repair(document_v02):
    documents = source_text(document_v02)
    document_v02.question_or_request.value[0].text.sources[0].quote = \
        "1. When will repairs start? a. Budget?"
    with pytest.raises(ProvenanceError, match="Quote not found"):
        validate_provenance(document_v02, documents)


@pytest.mark.parametrize("documents", [{}, {100: ()}, {100: (" \n",)}])
def test_missing_source_fails_even_if_every_field_unknown(document_v02_data, documents):
    for field in (*CORE_FIELDS, "document_role"):
        document_v02_data[field] = {"status": "unknown", "value": None, "reason": "not_in_document"}
    extraction = DocumentExtraction.model_validate(document_v02_data)
    with pytest.raises(ProvenanceError, match="Missing source text"):
        validate_provenance(extraction, documents)
