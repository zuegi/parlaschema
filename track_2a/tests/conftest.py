import pytest

from openparl_extractor.schema import CORE_FIELDS, DocumentExtraction, iter_evidence


def synthetic_fact(text, normalized=None, page=1):
    return {
        "original": text,
        "normalized": normalized,
        "sources": [{"document_id": 100, "quote": text, "page": page}],
    }


def known(value):
    return {"status": "known", "value": value}


@pytest.fixture
def document_data():
    return {
        "schema_version": "0.1", "affair_id": 10, "document_id": 100,
        "parliament": "TI", "language": "it",
        **{name: {"status": "unknown", "value": None, "reason": "not_in_document"}
           for name in CORE_FIELDS},
        "document_role": known(synthetic_fact("Response of Example Executive", "executive_response")),
        "affair_type": known(synthetic_fact("Interpellanza", "TI:interpellanza")),
        "title": known(synthetic_fact("Synthetic inquiry")),
        "submitters": known([{"name": synthetic_fact("Example Person")}]),
        "addressed_body": known([synthetic_fact("Example Executive")]),
        "question_or_request": known([
            {"id": "q1", "text": synthetic_fact("1. Explain plan.\na. Budget?\nb. Dates?")},
            {"id": "q2", "text": synthetic_fact("2. What next?")},
        ]),
        "executive_answer": known([
            {"id": "preamble", "text": synthetic_fact("General introduction.")},
            {"id": "a1", "text": synthetic_fact("Questions 1 and 2: Plan is pending."),
             "question_links": {
                 "target_ids": ["q1", "q2"],
                 "sources": [{"document_id": 100, "quote": "Questions 1 and 2:", "page": 1}],
             }},
        ]),
        "dates": known([{
            "id": "d1",
            "value": synthetic_fact("April 2030", {"iso": "2030-04", "precision": "month"}),
        }]),
    }


@pytest.fixture
def document(document_data):
    return DocumentExtraction.model_validate(document_data)


@pytest.fixture
def documents(document):
    return {100: ("\n".join(source.quote for source in iter_evidence(document)),)}
