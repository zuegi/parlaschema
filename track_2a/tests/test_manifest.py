import json
from collections import Counter
from pathlib import Path


# Frozen selection metadata; URL tokens are identifiers, not verified hashes.
EXPECTED = [
    (340314, 926604, "ZH", "de", "Anfrage", 48400,
     "90999c95047e4552b4a9f4ac2f5c04b3", "787cb143320d04b0e3743b8293b4966aef87206351e7a273d9c4342e4099bbd9"),
    (340302, 926592, "ZH", "de", "Postulat", 77965,
     "1d806302bb464d25ab84cfe82b0c37a5", "ea6fa2c869237756e988ef97abb17e2f41db064215920b65d0de18c59a7b6ff3"),
    (339469, 925453, "ZH", "de", "Motion", 49511,
     "44f10921aee94c41b6ee30e63d3e1a89", "0c478a5177cac3d23f1f14dc91e0a64aa62fdc6997780f64fd8551203b5b830e"),
    (336083, 902692, "ZH", "de", "Motion", 11178,
     "7b9d307d161e4ce7aa05ade0473f1ef8", "ef9fff1bc5ae60efa15e080c4dd26acb9d04b6b8e5cb01bb22d1891569a36479"),
    (336076, 902686, "ZH", "de", "Anfrage", 22949,
     "04fb987f75f14c14848e8dbe0ef2b648", "ce6c17b16895be2c97e60ac471430033a558a63511405a8490155053444db3ea"),
    (336076, 922604, "ZH", "de", "Anfrage", 97128,
     "1b1b914c3b834997b0634b9d80fc081b", "096cd342d8476db07ef0273c7efca5e3a80b9a4c74b53ad23f4a55a22fcb1847"),
    (336073, 902683, "ZH", "de", "Anfrage", 63825,
     "33c2d9f90c574e6d94991b170cc354cf", "600a4207a814ce594ad7c2622b3f5da1243704c4dce2212b71ed5dfa4aa56c49"),
    (336073, 921072, "ZH", "de", "Anfrage", 245336,
     "5db974dd22bb4cf2ac63d584b9b82c2f", "fc38c8c0fd622992f04bb7030a2d05113ac637d61f20f02a717787019c882943"),
    (336084, 902693, "ZH", "de", "Postulat", 19777,
     "98eaa90380cb4bcd9632ae8ee845d08a", "e94935149f15190a9bcddcb5bc58bed50eadba46f0a6fa6776c01f92d24700d4"),
    (228191, 541615, "VD", "fr", "Interpellation", 58039,
     "2321861", "c6edc6a4dbabdc00753daf803a6c6f3e20c697b6dbbdf1bf36a1230029348763"),
    (203260, 480176, "VD", "fr", "Décret/Loi", 1642102,
     "2308844", "9d36139133c3cfbe6221feb33fada10918607d286b57ce5dbce716c313bd3478"),
    (247403, 540642, "VD", "fr", "Décret/Loi", 1076814,
     "2321125", "214ceb46ebbef1bc19c97c14de97cb5bbe472fa14c0be3c99a827d7dacfc8c37"),
    (340662, 927204, "TI", "it", "Interrogazione", 370926,
     "185476", "212f1a3c855c46564afb9ef25b86950d926ad7a10047c0267bb05e87388320d4"),
    (340448, 926916, "TI", "it", "Interrogazione", 77499,
     "185455", "def66f64f2adf3194db6fec98a28808d39b234d16e5dffceb22df5a28b8303b8"),
    (340291, 926587, "TI", "it", "Interpellanza", 121699,
     "185441", "d70d956be4a305409bd8e67e84f5fe403878ea4a10c9674ed0cbe79f57ddf3bf"),
    (340293, 926586, "TI", "it", "Interpellanza", 122537,
     "185445", "41d3ef57aa8dea3b20388699f945ae7bfc2afada5b183662fad18dc8ad6a5466"),
]

SOURCE_TEMPLATES = {
    "ZH": "https://parlzhcdws.cmicloud.ch/parlzh5/cdws/Files/{}-332/1/pdf",
    "VD": "https://sieldocs.vd.ch/ecm/app18/service/siel/getContent?ID={}",
    "TI": "https://www4.ti.ch/user_librerie/php/GC/allegato.php?allid={}",
}
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "data" / "manifest.json"
DEVELOPMENT_AFFAIRS = {340291, 336076, 228191}
EXPECTED_DOCUMENT_ROLES = {
    926604: "filing",
    926592: "filing",
    925453: "filing",
    902692: "filing",
    902686: "filing",
    922604: "executive_response",
    902683: "filing",
    921072: "executive_response",
    902693: "filing",
    541615: "executive_response",
    480176: "unknown",
    540642: "unknown",
    927204: "filing",
    926916: "filing",
    926587: "filing",
    926586: "filing",
}
INSPECTION_PATH = MANIFEST_PATH.with_name("pdf-inspection.json")
EXPECTED_PAGE_COUNTS = {
    926587: 2, 902686: 2, 922604: 5, 541615: 4,
    926604: 1, 926592: 1, 925453: 1, 902692: 1, 902683: 1, 921072: 3,
    902693: 1, 480176: 34, 540642: 19, 927204: 4, 926916: 4, 926586: 3,
}


def test_manifest_selection() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    documents = manifest["documents"]
    assert manifest["version"] == "2"
    assert manifest["verification_basis"] == "historical_reference"
    assert manifest["pdf_redistribution_rights"] == "pending"
    assert manifest["parser_and_scan_suitability"] == "pending"
    assert len(documents) == len({doc["document_id"] for doc in documents}) == 16
    assert len({doc["affair_id"] for doc in documents}) == 14
    assert Counter(doc["language"] for doc in documents) == {"de": 9, "fr": 3, "it": 4}
    assert {(doc["affair_id"], doc["document_id"]) for doc in documents} == {
        (row[0], row[1]) for row in EXPECTED
    }
    by_id = {doc["document_id"]: doc for doc in documents}
    for row in EXPECTED:
        assert_document(by_id[row[1]], row)


def assert_document(document: dict, expected: tuple) -> None:
    affair, doc_id, parliament, language, affair_type, size, source, mirror = expected
    assert {key: value for key, value in document.items() if not key.endswith("_check")} == {
        "affair_id": affair,
        "split": "development" if affair in DEVELOPMENT_AFFAIRS else "heldout",
        "document_id": doc_id,
        "document_role": EXPECTED_DOCUMENT_ROLES[doc_id],
        "parliament": parliament,
        "language": language,
        "government_level": "canton",
        "affair_type_original": affair_type,
        "source_url": SOURCE_TEMPLATES[parliament].format(source),
        "download_url": f"https://files.openparldata.ch/doc/{parliament}/{mirror}",
        "metadata_api_url": f"https://api.openparldata.ch/v1/affairs/{affair}/docs",
        "checked_on": "2026-10-05",
        "api_text_available": True,
    }
    assert_checks(document, parliament, size)


def assert_checks(document: dict, parliament: str, size: int) -> None:
    assert document["source_check"] == {
        "http_status": 206 if parliament == "VD" else 200,
        "bytes_read_up_to": 1024,
        "pdf_signature_verified": True,
    }
    assert document["download_check"] == {
        "http_status": 200,
        "fully_retrieved": True,
        "pdf_signature_verified": True,
        "size_bytes": size,
    }


def test_split_keeps_all_documents_of_each_affair_together() -> None:
    documents = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["documents"]
    splits_by_affair: dict[int, set[str]] = {}
    for document in documents:
        splits_by_affair.setdefault(document["affair_id"], set()).add(document["split"])
    assert all(len(splits) == 1 for splits in splits_by_affair.values())
    assert {affair for affair, splits in splits_by_affair.items()
            if splits == {"development"}} == DEVELOPMENT_AFFAIRS
    assert Counter(doc["split"] for doc in documents) == {"development": 4, "heldout": 12}
    assert Counter(next(iter(splits)) for splits in splits_by_affair.values()) == {
        "development": 3, "heldout": 11,
    }


def test_document_roles_match_selection_reference() -> None:
    documents = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["documents"]
    assert {doc["document_id"]: doc["document_role"] for doc in documents} == (
        EXPECTED_DOCUMENT_ROLES
    )
    assert Counter(doc["document_role"] for doc in documents) == {
        "filing": 11, "executive_response": 3, "unknown": 2,
    }


def test_pdf_inspection_selection_and_splits() -> None:
    inspection = json.loads(INSPECTION_PATH.read_text(encoding="utf-8"))
    documents = inspection["documents"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["documents"]
    assert len(documents) == len({doc["document_id"] for doc in documents}) == 16
    assert {doc["document_id"]: doc["page_count"] for doc in documents} == EXPECTED_PAGE_COUNTS
    assert {doc["document_id"]: doc["split"] for doc in documents} == {
        doc["document_id"]: doc["split"] for doc in manifest
    }
    for split, expected in inspection["groups"].items():
        group = [doc for doc in documents if doc["split"] == split]
        assert len(group) == expected["documents"] == expected["private_machine_drafts"]
        assert sum(doc["page_count"] for doc in group) == expected["pages"]
        assert expected["human_approved"] == 0


def test_pdf_inspection_preserves_review_boundaries() -> None:
    inspection = json.loads(INSPECTION_PATH.read_text(encoding="utf-8"))
    assert inspection["version"] == "1"
    assert inspection["checked_on"] == "2026-10-07"
    assert inspection["reviewer_kind"] == "machine"
    assert inspection["verification_basis"] == "retrieved_bytes_and_local_tools"
    for boundary in ("full_character_level_visual_review", "semantic_completeness",
                     "human_review", "publication_permission"):
        assert inspection["boundaries"][boundary] == "pending"
    assert inspection["boundaries"]["heldout_used_for_prompt_or_schema_tuning"] is False
    assert inspection["boundaries"]["private_sources_and_annotations_in_repository"] is False
    assert all(doc["annotation_state"] == "draft" for doc in inspection["documents"])


def test_pdf_inspection_text_agreement_and_ocr_scope() -> None:
    documents = json.loads(INSPECTION_PATH.read_text(encoding="utf-8"))["documents"]
    assert {doc["document_id"] for doc in documents
            if doc["api_whitespace_stripped_text_equal"]} == {926587, 927204, 926916, 926586}
    assert {doc["document_id"]: doc["poppler_blank_text_pages"] for doc in documents
            if doc["poppler_blank_text_pages"]} == {480176: [32, 33, 34], 540642: [19]}
    for doc in documents:
        assert doc["ocr_pages_processed"] == doc["poppler_blank_text_pages"]
        assert all(1 <= page <= doc["page_count"] for page in doc["ocr_pages_processed"])
        assert doc["pdf_word_tokens_missing_from_api"] >= 0
        if doc["api_whitespace_stripped_text_equal"]:
            assert doc["pdf_word_tokens_missing_from_api"] == 0
