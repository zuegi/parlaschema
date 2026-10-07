import pytest

from openparl_extractor.provenance import ProvenanceError, validate_evidence, validate_provenance
from openparl_extractor.schema import CORE_FIELDS, DocumentExtraction, Evidence, iter_evidence


def test_supplied_document_text_only(document, documents):
    validate_provenance(document, documents)


@pytest.mark.parametrize("page", [1, None])
def test_known_or_unknown_page(page):
    validate_evidence(Evidence(document_id=100, quote="Exact quote", page=page), {100: ("Exact quote",)})


def test_known_page_must_contain_quote():
    source = Evidence(document_id=100, quote="Page two", page=1)
    with pytest.raises(ProvenanceError, match="Quote not found"):
        validate_evidence(source, {100: ("Page one", "Page two")})


def test_page_outside_document():
    source = Evidence(document_id=100, quote="Source", page=2)
    with pytest.raises(ProvenanceError, match="outside document"):
        validate_evidence(source, {100: ("Source",)})


@pytest.mark.parametrize("documents", [
    {}, {100: ()}, {101: ("other",)}, {100: ("",)}, {100: (" \n", "")},
])
def test_missing_document_fails_even_when_all_fields_unknown(document_data, documents):
    for name in [*CORE_FIELDS, "document_role"]:
        document_data[name] = {"status": "unknown", "value": None, "reason": "not_in_document"}
    document = DocumentExtraction.model_validate(document_data)
    with pytest.raises(ProvenanceError, match="Missing source text"):
        validate_provenance(document, documents)


def test_no_fuzzy_quote_matching():
    source = Evidence(document_id=100, quote="Normal space")
    with pytest.raises(ProvenanceError, match="Quote not found"):
        validate_evidence(source, {100: ("Normal  space",)})


def test_unknown_page_preserves_page_boundaries():
    source = Evidence(document_id=100, quote="One\fTwo")
    validate_evidence(source, {100: ("One", "Two")})
    with pytest.raises(ProvenanceError):
        validate_evidence(Evidence(document_id=100, quote="OneTwo"), {100: ("One", "Two")})


def test_occurrence_is_not_semantic_entailment(document_data):
    document_data["title"]["value"]["original"] = "Unsupported title interpretation"
    document_data["title"]["value"]["sources"] = [
        {"document_id": 100, "quote": "Actual source title", "page": None},
    ]
    document = DocumentExtraction.model_validate(document_data)
    text = "\n".join(source.quote for source in document.title.value.sources)
    all_text = "\n".join(source.quote for source in iter_evidence(document))
    validate_provenance(document, {100: (all_text,)})
    assert document.title.value.original not in text
