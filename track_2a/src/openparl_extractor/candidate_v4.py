import json
import re
from typing import Any, Literal

from pydantic import ValidationError, model_validator

from openparl_extractor import candidate_v3
from openparl_extractor.candidates import Anchor, CandidateField, CandidateSet, Stream
from openparl_extractor.range_selection import parse_json_object
from openparl_extractor.source_document import SourceDocument
from openparl_extractor.span_selection import SelectionError

VERSION = "candidate-contract-v4-offline"
QuestionKind = Literal["question", "request"]
INTERROGATIVE = re.compile(
    r"(?i)(?:^|[.!?:,]\s+)(?:wie|was|welche[rns]?|wer|wann|wo|warum|wieso|"
    r"hat|haben|ist|sind|gibt|gehen|kann|können|wird|werden|"
    r"quel(?:le)?s?|comment|pourquoi|quand|où|est-ce|"
    r"come|qual[ei]|quando|perché)\b"
)
FRENCH_INVERSION = re.compile(r"(?i)\b(?:t-il|t-elle|comprend-elle|prévoit-il)\b")
ITALIAN_INVERSION = re.compile(r"(?i)^(?:il cantone|il decs|il consiglio)\s+(?:dispone|monitora|intende)\b")
REQUEST = re.compile(
    r"(?i)^\s*(?:der regierungsrat wird (?:aufgefordert|ersucht)|"
    r"le conseil d['’]état est (?:invité|prié)|"
    r"il consiglio di stato è invitato|si chiede (?:di|che))\b"
)
INSTRUMENT_LABEL = re.compile(
    r"(?i)^\s*(?:\d+\.\s*)?(?:anfrage|interpellation|interpellanza|motion|postulat)\b"
)
COMPLETE_TITLE_RULES = {
    "title.label-to-block-end", "title.parenthesized-after-instrument",
    "title.dash-until-reference", "title.early-isolated-layout",
}
SYSTEM = (
    "Select only supplied candidate ids, categories and evidence ids. Output one compact JSON object "
    "with status, reason, status_evidence, items; property order is irrelevant. No free text. "
    "Every item has id, category and evidence. known requires supported complete values and null reason; "
    "positive status_evidence is allowed if linked and supporting. partial requires a source-supported "
    "limit and reason unenumerated_members or incomplete. needs_review uses reason ambiguous. "
    "not_found uses reason not_found and empty items/status_evidence: not proof of document absence. "
    "Evidence is not a selectable replacement value. Never repair or change source text, "
    "sort, duplicate, merge independent numbered blocks or invent identities/categories."
)
FIELD_INSTRUCTIONS: dict[CandidateField, str] = {
    "title": (
        "Choose one smallest complete affair title. title_role full_title is a rule-based candidate hint, "
        "not proof; read the text and linked evidence. heading_fragment omits a continuation and "
        "instrument_label includes instrument/number wording: neither is a full original title. "
        "Do not choose a fragment when its continuation is supplied. category null."
    ),
    "submitters": (
        "Select named submitters only with explicit linked submission context, category submitter "
        "(null and needs_review for genuine ambiguity). Read group_hints: visible unnamed consorts "
        "requires partial + unenumerated_members and the associated evidence in status_evidence, "
        "not known. Never invent unnamed members; known only for an evidenced complete named list. "
        "Same-name different contexts are alternatives, not permission to output the person twice."
    ),
    "question_or_request": (
        "Select every complete main block including its subquestions. Prefer the complete composite "
        "main_item when children are contained; never select that parent and children together. "
        "Choosing children alone omits any parent-only question text and cannot claim known completeness. "
        "Each candidate provides closed allowed_kinds from conservative source classification. "
        "Use the evidenced question/request kind when unambiguous; choose only supplied kinds. "
        "Null only for genuine ambiguity with needs_review, never omit an explicit classified kind. "
        "Do not select answers, duplicate children or merge independent numbered blocks."
    ),
}


class Selection(candidate_v3.Selection):
    @model_validator(mode="after")
    def check_status(self) -> "Selection":
        if self.status == "known" and (self.reason is not None or not self.items):
            raise ValueError("known requires items and null reason")
        if self.status == "not_found" and (self.reason != "not_found" or self.items or self.status_evidence):
            raise ValueError("not_found requires empty items/status_evidence and matching reason")
        if self.status == "partial" and (
            not self.items or self.reason not in ("unenumerated_members", "incomplete") or not self.status_evidence
        ):
            raise ValueError("partial requires items, limited reason and status evidence")
        if self.status == "needs_review" and self.reason != "ambiguous":
            raise ValueError("needs_review requires reason ambiguous")
        return self


def classify_kind(text: str) -> tuple[QuestionKind | None, str]:
    compact = " ".join(text.split())
    request = bool(REQUEST.search(compact))
    question = "?" in compact and bool(
        INTERROGATIVE.search(compact) or FRENCH_INVERSION.search(compact) or ITALIAN_INVERSION.search(compact)
    )
    if request and not question:
        return "request", "explicit_request_formula"
    if question and not request:
        return "question", "interrogative_word_or_inversion_and_question_mark"
    return None, "ambiguous_or_no_supported_formula"


def _bounds(stream: Stream, value: dict[str, Any]) -> tuple[int, int]:
    member = value["members"][0]
    return stream.index(Anchor.model_validate(member["start"])), stream.index(Anchor.model_validate(member["end"]))


def build_input(document: SourceDocument, candidates: CandidateSet, field: CandidateField) -> dict[str, Any]:
    data = candidate_v3.build_input(document, candidates, field)
    data["version"] = VERSION
    data["group_hints"] = [
        {"candidate_id": e["candidate_id"], "evidence_id": e["id"], "limit": "unenumerated_members"}
        for e in data["evidence"] if field == "submitters" and e["unnamed_group_hint"]
    ]
    stream = Stream(document)
    rules = {candidate.id: candidate.rule for candidate in candidates.candidates}
    for value in data["values"]:
        if field == "title":
            value["title_role"] = _title_role(stream, value, data["values"], rules)
        elif field == "question_or_request":
            kind, rule = classify_kind(value["text"])
            value.update({"kind": kind, "block_role": value.pop("kind"), "kind_rule": rule,
                          "allowed_kinds": [kind], "parent_id": None})
    if field == "question_or_request":
        _question_relations(stream, data["values"])
    return data


def _title_role(
    stream: Stream, value: dict[str, Any], values: list[dict[str, Any]], rules: dict[str, str],
) -> str:
    start, end = _bounds(stream, value)
    if any(_bounds(stream, other)[0] <= start and _bounds(stream, other)[1] > end
           and other["text"].startswith(value["text"]) for other in values if other is not value):
        return "heading_fragment"
    rule = rules[value["members"][0]["candidate_id"]]
    if rule not in COMPLETE_TITLE_RULES and INSTRUMENT_LABEL.match(value["text"]):
        return "instrument_label"
    # A layout candidate containing an instrument prefix remains label-bearing.
    if INSTRUMENT_LABEL.match(value["text"]):
        return "instrument_label"
    return "full_title" if rule in COMPLETE_TITLE_RULES else "heading"


def _question_relations(stream: Stream, values: list[dict[str, Any]]) -> None:
    for child in values:
        if child["block_role"] != "subitem":
            continue
        start, end = _bounds(stream, child)
        parents = [p for p in values if p["block_role"] == "main_item"
                   and _bounds(stream, p)[0] <= start and end <= _bounds(stream, p)[1]]
        if len(parents) != 1:
            continue
        parent = parents[0]
        child["parent_id"] = parent["id"]
        # Declarative breakdown labels remain ambiguous, not classified just by parent membership.
    for parent in values:
        parent["child_ids"] = [v["id"] for v in values if v["parent_id"] == parent["id"]]


def parse_selection(content: str) -> Selection:
    try:
        return Selection.model_validate(parse_json_object(content))
    except ValidationError as error:
        raise SelectionError(f"Invalid v4 output: {error}") from error


def build_result(document: SourceDocument, data: dict[str, Any], selection: Selection) -> dict[str, Any]:
    if data["version"] != VERSION:
        raise SelectionError("Requires v4 input")
    values = {value["id"]: value for value in data["values"]}
    selected_ids = {item.id for item in selection.items}
    for item in selection.items:
        if item.id not in values:
            raise SelectionError("Unknown candidate id")
        value = values[item.id]
        if data["field"] == "question_or_request":
            if item.category not in value["allowed_kinds"]:
                raise SelectionError("Kind must match closed source classification")
            if value["parent_id"] and value["parent_id"] in selected_ids:
                raise SelectionError("Parent and contained subitem cannot both be selected")
            if value["parent_id"] and selection.status == "known":
                raise SelectionError("Subitems alone do not establish complete parent question")
        if data["field"] == "title" and selection.status == "known" and value["title_role"] in (
            "heading_fragment", "instrument_label",
        ):
            raise SelectionError("known title cannot be a fragment or instrument label")
    _group_consistency(data, selection, selected_ids)
    result = candidate_v3.build_result(document, data, selection)
    result["procedure"] = VERSION
    return result


def _group_consistency(data: dict[str, Any], selection: Selection, selected: set[str]) -> None:
    hints = [hint for hint in data["group_hints"] if hint["candidate_id"] in selected]
    if not hints:
        return
    if selection.status != "partial" or selection.reason != "unenumerated_members":
        raise SelectionError("Visible unnamed group requires partial/unenumerated_members")
    if not any(hint["evidence_id"] in selection.status_evidence for hint in hints):
        raise SelectionError("Unnamed group requires associated status evidence")


def request_body(model: str, data: dict[str, Any]) -> dict[str, Any]:
    schema = candidate_v3.response_schema(data)
    field = data["field"]
    return {
        "model": model, "temperature": 0, "top_p": 1, "max_tokens": candidate_v3.MAX_TOKENS[field],
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content":
            f"Field: {field}\n{FIELD_INSTRUCTIONS[field]}\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": f"{field}_candidate_v4", "strict": True, "schema": schema,
        }},
    }
