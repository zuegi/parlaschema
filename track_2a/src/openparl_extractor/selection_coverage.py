import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from openparl_extractor import candidate_v3
from openparl_extractor.candidate_v4 import VERSION as V4_VERSION, _question_relations, classify_kind
from openparl_extractor.candidates import Anchor, Stream
from openparl_extractor.range_selection import parse_json_object
from openparl_extractor.selection_run import payload_hash
from openparl_extractor.source_document import SourceDocument
from openparl_extractor.span_selection import SelectionError

VERSION = "selection-coverage-v1-offline"


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    evidence: list[str]
    interpretation: Literal["submitter", "question", "request"] | None = None


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: list[Item]


def parse_selection(content: str) -> Selection:
    try:
        return Selection.model_validate(parse_json_object(content))
    except ValidationError as error:
        raise SelectionError(f"Invalid selection transport: {error}") from error


def _inventory(document: SourceDocument) -> dict[str, Any]:
    return {
        "source_document_hash": payload_hash(document.model_dump(mode="json")),
        "pdf_sha256": document.sha256, "extraction_method": document.extraction_method,
        "pages": [{"page": page.number,
                   "span_ids": [s.id for b in page.blocks for s in b.spans],
                   "sources": list(dict.fromkeys(s.source for b in page.blocks for s in b.spans))}
                  for page in document.pages],
        "warnings": [w.model_dump(mode="json") for w in document.warnings],
        "pdf_page_count_verified": False,
    }


def build_input(document: SourceDocument, frozen_v4: dict[str, Any]) -> dict[str, Any]:
    if frozen_v4["version"] != V4_VERSION or frozen_v4["document_id"] != document.document_id:
        raise SelectionError("Requires matching frozen v4 input")
    data = copy.deepcopy(frozen_v4)
    data.update(version=VERSION, parent_input_hash=payload_hash(frozen_v4),
                source_inventory=_inventory(document))
    _verify_input(document, data)
    return data


def _verify_input(document: SourceDocument, data: dict[str, Any]) -> None:
    if data["version"] != VERSION or data["document_id"] != document.document_id:
        raise SelectionError("Document/input version mismatch")
    if data["source_inventory"] != _inventory(document):
        raise SelectionError("Source page inventory differs from document")
    values, sources = data["values"], data["evidence"]
    if len({v["id"] for v in values}) != len(values) or len({e["id"] for e in sources}) != len(sources):
        raise SelectionError("Duplicate input ids")
    candidate_v3._verify_sources(document, sources)
    source_map = {e["id"]: e for e in sources}
    for value in values:
        _verify_value(document, data["field"], value, source_map)
    if data["field"] == "question_or_request":
        derived = copy.deepcopy(values)
        _question_relations(Stream(document), derived)
        if derived != values:
            raise SelectionError("Parent/child relationships differ from source offsets")
    _verify_group_hints(data, source_map)


def _verify_value(document: SourceDocument, field: str, value: dict[str, Any], sources: dict) -> None:
    if not value["members"]:
        raise SelectionError("Candidate requires source members")
    candidate_v3._verify_sources(document, value["members"])
    if any(m["text"] != value["text"] for m in value["members"]):
        raise SelectionError("Candidate text differs from source member")
    if not value["evidence_ids"] or any(
        eid not in sources or sources[eid]["candidate_id"] != value["id"] for eid in value["evidence_ids"]
    ):
        raise SelectionError("Candidate evidence association differs")
    if field == "question_or_request":
        kind, rule = classify_kind(value["text"])
        if (value["kind"], value["kind_rule"], value["allowed_kinds"]) != (kind, rule, [kind]):
            raise SelectionError("Supplied kind differs from source classification")


def _verify_group_hints(data: dict[str, Any], sources: dict) -> None:
    expected = []
    for source in sources.values():
        group = bool(candidate_v3.UNNAMED.search(source["text"]))
        explicit = data["field"] == "submitters" and bool(candidate_v3.SUBMISSION.search(source["text"]))
        if source["unnamed_group_hint"] != group or source["submission_context_hint"] != explicit:
            raise SelectionError("Source context hint differs from text")
        if group and data["field"] == "submitters":
            expected.append({"candidate_id": source["candidate_id"], "evidence_id": source["id"],
                             "limit": "unenumerated_members"})
    if expected != data["group_hints"]:
        raise SelectionError("Group hints differ from source evidence")


def _category(field: str, item: Item, value: dict, sources: list[dict]) -> dict[str, Any]:
    if field == "title":
        if item.interpretation is not None:
            raise SelectionError("Title has no interpretation category")
        if value["title_role"] in ("heading_fragment", "instrument_label"):
            raise SelectionError("Selected title is a fragment or instrument label")
        return {"category": None, "origin": "not_applicable"}
    if field == "submitters":
        if item.interpretation not in (None, "submitter"):
            raise SelectionError("Invalid submitter interpretation")
        if item.interpretation == "submitter" and not any(s["submission_context_hint"] for s in sources):
            raise SelectionError("Role requires explicit associated submission context")
        return {"category": item.interpretation,
                "origin": "model_interpretation" if item.interpretation else "unresolved_role"}
    if value["kind"] is not None:
        if item.interpretation is not None:
            raise SelectionError("Clear kind must not be redundantly model supplied")
        return {"category": value["kind"], "origin": "code-derived",
                "rule": value["kind_rule"], "evidence_ids": item.evidence}
    if item.interpretation is not None:
        raise SelectionError("Interpretation requires separately verifiable semantic kind evidence")
    return {"category": None, "origin": "heuristic_gap_or_ambiguity_unverified"}


def build_result(document: SourceDocument, data: dict[str, Any], selection: Selection) -> dict[str, Any]:
    _verify_input(document, data)
    values, evidence = {v["id"]: v for v in data["values"]}, {e["id"]: e for e in data["evidence"]}
    if data["field"] == "title" and len(selection.items) > 1:
        raise SelectionError("At most one title")
    results, categories, seen = [], [], set()
    previous, stream = -1, Stream(document)
    for item in selection.items:
        if item.id not in values or item.id in seen:
            raise SelectionError("Unknown or duplicate candidate id")
        value = values[item.id]
        sources = candidate_v3._linked_evidence(item, value, evidence)
        category = _category(data["field"], item, value, sources)
        previous = _check_order(stream, value, previous, results, data["field"])
        seen.add(item.id)
        results.append({"id": item.id, "text": value["text"], "provenance": value["members"],
                        "evidence": sources})
        categories.append({"id": item.id, **category})
    return {"procedure": VERSION, "selection_integrity": "validated",
            "selection_state": "selection_present" if results else "no_selection",
            "original_values": results, "categories": categories,
            "coverage": coverage_protocol(data, selection, categories)}


def _check_order(stream: Stream, value: dict, previous: int, results: list, field: str) -> int:
    member = value["members"][0]
    start, end = Anchor.model_validate(member["start"]), Anchor.model_validate(member["end"])
    if stream.index(start) < previous:
        raise SelectionError("Selection overlaps or precedes previous block")
    if field == "submitters" and value["text"] in {v["text"] for v in results}:
        raise SelectionError("Duplicate person value from ungrouped sources")
    return stream.index(end)


def coverage_protocol(data: dict, selection: Selection, categories: list[dict]) -> dict[str, Any]:
    selected = {item.id for item in selection.items}
    ranges = [{"origin": "candidate_member", "id": v["id"], **m}
              for v in data["values"] for m in v["members"]]
    ranges += [{"origin": "context_evidence", **e} for e in data["evidence"]]
    pages = sorted({p for r in ranges for p in r["pages"]})
    source_pages = [p["page"] for p in data["source_inventory"]["pages"]]
    return {
        "input_version": data["version"], "input_hash": payload_hash(data),
        "parent_input_hash": data["parent_input_hash"], "source_inventory": data["source_inventory"],
        "presented_ranges": ranges, "presented_pages": pages,
        "unpresented_source_pages": [p for p in source_pages if p not in pages],
        "candidate_ledger": _candidate_ledger(data, selected),
        "machine_coverage": {"input_candidates_validated": len(data["values"]),
                             "selected": len(selected), "model_attention_verified": False},
        "group_limits": [{**h, "selected_person": h["candidate_id"] in selected} for h in data["group_hints"]],
        "open_interpretations": [c for c in categories if c["category"] is None
                                and c["origin"] != "not_applicable"],
        "unclassified_candidates": [v["id"] for v in data["values"]
                                    if data["field"] == "question_or_request" and v["kind"] is None],
        "semantic_coverage": "unverified", "semantic_review": None,
        "limitations": ["candidate_generation_recall_unverified", "document_completeness_unverified",
                        "no_selection_is_not_document_absence", "source_hints_are_not_semantic_review"],
    }


def _candidate_ledger(data: dict, selected: set[str]) -> list[dict[str, Any]]:
    return [{"id": v["id"], "selected": v["id"] in selected,
             "parent_id": v.get("parent_id"), "child_ids": v.get("child_ids", []),
             "source_notes": v["notes"], "supplied_kind": v.get("kind") if data["field"] == "question_or_request" else None,
             "kind_rule": v.get("kind_rule"), "title_role": v.get("title_role")}
            for v in data["values"]]


def project_v4(raw: dict[str, Any], data: dict[str, Any]) -> tuple[Selection, dict[str, Any]]:
    values = {v["id"]: v for v in data["values"]}
    sources = {s["id"]: s for s in data["evidence"]}
    status_ids = raw["status_evidence"]
    chosen_ids = {item["id"] for item in raw["items"]}
    if len(status_ids) != len(set(status_ids)) or any(
        eid not in sources or sources[eid]["candidate_id"] not in chosen_ids for eid in status_ids
    ):
        raise SelectionError("Invalid discarded status evidence association")
    items = []
    for item in raw["items"]:
        if item["id"] not in values:
            raise SelectionError("Unknown candidate in diagnostic replay")
        clear = data["field"] == "question_or_request" and values[item["id"]]["kind"] is not None
        if clear and item["category"] not in (None, values[item["id"]]["kind"]):
            raise SelectionError("Raw category contradicts supplied clear kind")
        items.append({"id": item["id"], "evidence": item["evidence"],
                      "interpretation": None if clear else item["category"]})
    return Selection.model_validate({"items": items}), {
        "diagnostic_only": True, "unchanged_raw_items": raw["items"],
        "discarded_model_decision": {k: raw[k] for k in ("status", "reason", "status_evidence")},
        "redundant_kind_removed": [item["id"] for item in raw["items"]
                                  if data["field"] == "question_or_request"
                                  and values[item["id"]]["kind"] is not None],
    }
