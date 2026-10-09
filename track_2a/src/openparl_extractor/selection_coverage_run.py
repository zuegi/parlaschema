import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from openparl_extractor.candidate_run import DEVELOPMENT_DOCUMENTS
from openparl_extractor.candidate_v4_run import load_snapshot
from openparl_extractor.candidates import CANDIDATE_FIELDS
from openparl_extractor.selection_coverage import VERSION, build_input, build_result, coverage_protocol, project_v4
from openparl_extractor.source_document import SourceDocument
from openparl_extractor.span_selection import SelectionError

OUTPUT = Path("output/analysis/selection_coverage_v1_offline")
METHOD = """# Selection/coverage v1: pre-evaluation method
Offline only. Existing v4 value/evidence ids and offsets retained in versioned inputs.
Transport items have id, evidence and optional necessary interpretation. No global status.
Clear supplied kind is code-derived; heuristic gaps remain unresolved, not proven ambiguity.
Invalid ids, provenance, duplicate people, ordering and overlaps remain errors.
Unverifiable non-null interpretations are rejected, never guessed or silently accepted.
Coverage is a separate input/source inventory, not field completeness or absence.
semantic_coverage always unverified; no semantic_review is fabricated from Dev evaluation.
Reference counts/text matches are historical independent offline evaluation, never approval.
Read-only raw replay explicitly projects redundant fields, retains raw decision separately.
Original v4 scores/artefacts remain unchanged; no new model result or Domain score.
Freeze method/code/tests/docs/versioned inputs/source documents before any raw replay.
Report all twelve fields, failures included. Expected prior hypothesis nine integral selections;
any discrepancy must be explained, never bypass a check to recover the hypothesis.
"""


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _verify(root: Path) -> None:
    for name, sha in json.loads((root / "SHA256SUMS.json").read_text()).items():
        if _hash(root / name) != sha:
            raise SelectionError(f"Offline freeze differs: {name}")


def prepare(root: Path = OUTPUT) -> None:
    requests = load_snapshot()
    snapshot = root / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=False)
    (snapshot / "method.md").write_text(METHOD, encoding="utf-8")
    for document, frozen, _ in requests:
        data = build_input(document, frozen)
        _write(snapshot / f"{document.document_id}-{data['field']}.input.json", data)
        _write(snapshot / f"{document.document_id}.source.json", document.model_dump(mode="json"))
    for name in ("src/openparl_extractor/selection_coverage.py",
                 "src/openparl_extractor/selection_coverage_run.py",
                 "tests/test_selection_coverage.py", "docs/selection_coverage.md"):
        path = Path(name)
        (snapshot / path.name).write_bytes(path.read_bytes())
    _write(snapshot / "SHA256SUMS.json", {p.name: _hash(p) for p in snapshot.iterdir()})
    _protect(root)


def _protect(root: Path) -> None:
    previous = Path("output/analysis/v4_simplification_diagnostic")
    files = json.loads((previous / "protected_before.json").read_text())
    for path in previous.iterdir():
        if path.is_file():
            files[str(path)] = _hash(path)
    for name, sha in files.items():
        if _hash(Path(name)) != sha:
            raise SelectionError(f"Protected historical file differs: {name}")
    _write(root / "protected_before.json", files)


def _replay(document: SourceDocument, data: dict, raw: dict) -> dict[str, Any]:
    chosen, projection = project_v4(raw, data)
    record = {"procedure": VERSION, "diagnostic_only": True, "projection": projection,
              "integrity": "failed", "error": None, "result": None}
    try:
        record["result"] = build_result(document, data, chosen)
        record["coverage"] = record["result"]["coverage"]
        record["integrity"] = "validated"
    except SelectionError as error:
        record["error"] = str(error)
        record["coverage"] = coverage_protocol(data, chosen, [])
    return record


def replay(root: Path = OUTPUT) -> None:
    snapshot = root / "snapshot"
    _verify(snapshot)
    target = root / "replay"
    target.mkdir(exist_ok=False)
    old = json.loads(Path("output/selection_candidates_v4/assessment.json").read_text())
    matrix = []
    paths = sorted(snapshot.glob("*.input.json"))
    expected = {f"{did}-{field}.input.json" for did in DEVELOPMENT_DOCUMENTS for field in CANDIDATE_FIELDS}
    if {p.name for p in paths} != expected:
        raise SelectionError("Requires all twelve frozen Dev field inputs")
    for path in paths:
        data = json.loads(path.read_text())
        document = SourceDocument.model_validate_json(
            (snapshot / f"{data['document_id']}.source.json").read_text())
        logpath = Path("output/selection_candidates_v4") / path.name.replace(".input", "")
        log = json.loads(logpath.read_text())
        if log["input_hash"] != data["parent_input_hash"]:
            raise SelectionError("Raw log input differs from frozen parent")
        raw = json.loads(log["raw_response"]["choices"][0]["message"]["content"])
        record = _replay(document, data, raw)
        original = next(r for r in old["fields"] if (r["document_id"], r["field"])
                        == (data["document_id"], data["field"]))
        record["dev_reference_evaluation_separate"] = _evaluation(original)
        _write(target / path.name.replace(".input", ""), record)
        matrix.append({"document_id": data["document_id"], "field": data["field"],
                       "integrity": record["integrity"], "remaining_error": record["error"],
                       "semantic_coverage": record["coverage"]["semantic_coverage"],
                       "dev_reference_evaluation_separate": _evaluation(original),
                       "domain_status_completeness": "not_delivered"})
    _write(root / "matrix.json", matrix)
    _verify_protected(root)
    print(f"{sum(r['integrity'] == 'validated' for r in matrix)}/12 diagnostic selection integrity; semantic unverified")


def _evaluation(original: dict) -> dict[str, Any]:
    return {"origin": "historical_v4_offline_dev_evaluation_not_semantic_approval",
            "original_technical": original["technical"], "original_full_point": original["full_field_point"],
            "strict_value_matches": original["strict_content_matches"],
            "diagnostic_rejoin_matches": original["diagnostic_content_matches"],
            "reference_items": original["reference_count"], "original_finding": original["manual_decision"]}


def _verify_protected(root: Path) -> None:
    files = json.loads((root / "protected_before.json").read_text())
    for name, sha in files.items():
        if _hash(Path(name)) != sha:
            raise SelectionError(f"Historical file changed: {name}")
    _write(root / "verification.json", {"protected_unchanged": len(files), "snapshot_verified": True,
                                      "live_calls": 0, "no_new_model_results": True})


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline-only selection/coverage freeze and diagnostic replay")
    parser.add_argument("operation", choices=("prepare", "replay"))
    parser.add_argument("--out-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.out_dir)
    else:
        replay(args.out_dir)


if __name__ == "__main__":
    main()
