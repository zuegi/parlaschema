import argparse
import sys
from pathlib import Path

from openparl_extractor.config import ConfigError, load_llm_config


def check_config() -> int:
    try:
        config = load_llm_config()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"LLM configuration valid: {config.name} at {config.base_url}")
    return 0


def extract_source(args: argparse.Namespace) -> int:
    from openparl_extractor.pdf_extraction import NotAPdfError, extract_source_document

    try:
        document = extract_source_document(args.pdf, args.document_id, args.affair_id)
    except (NotAPdfError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / f"{args.document_id}.source.json"
    target.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    spans = sum(len(block.spans) for page in document.pages for block in page.blocks)
    print(f"{target}: {len(document.pages)} pages, {spans} spans, {len(document.warnings)} warnings")
    return 0


def select_fields(args: argparse.Namespace) -> int:
    from openparl_extractor.selection_run import MAX_LIVE_REQUESTS, HttpChatClient, run_documents
    from openparl_extractor.source_document import SourceDocument
    from openparl_extractor.span_selection import FIELD_NAMES

    try:
        config = load_llm_config()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    documents = [SourceDocument.model_validate_json(p.read_text(encoding="utf-8")) for p in args.source_json]
    if len(documents) * len(FIELD_NAMES) > MAX_LIVE_REQUESTS:
        print(f"Refusing: more than {MAX_LIVE_REQUESTS} requests", file=sys.stderr)
        return 1
    records = run_documents(HttpChatClient(config), config.name, documents, args.out_dir)
    valid = sum(r["outcome"] == "valid" for r in records)
    print(f"{args.out_dir}: {valid}/{len(records)} valid")
    return 0


def select_ranges(args: argparse.Namespace) -> int:
    from openparl_extractor.range_run import run_documents
    from openparl_extractor.selection_run import MAX_LIVE_REQUESTS, HttpChatClient
    from openparl_extractor.source_document import SourceDocument
    from openparl_extractor.span_selection import FIELD_NAMES

    try:
        config = load_llm_config()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    documents = [SourceDocument.model_validate_json(p.read_text(encoding="utf-8")) for p in args.source_json]
    if len(documents) * len(FIELD_NAMES) > MAX_LIVE_REQUESTS:
        print(f"Refusing: more than {MAX_LIVE_REQUESTS} requests", file=sys.stderr)
        return 1
    records = run_documents(HttpChatClient(config), config.name, documents, args.out_dir)
    valid = sum(r["outcome"] == "valid" for r in records)
    print(f"{args.out_dir}: {valid}/{len(records)} valid")
    return 0


def generate_candidates_command(args: argparse.Namespace) -> int:
    from openparl_extractor.candidates import generate_candidates
    from openparl_extractor.source_document import SourceDocument

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for path in args.source_json:
        document = SourceDocument.model_validate_json(path.read_text(encoding="utf-8"))
        result = generate_candidates(document)
        target = args.out_dir / f"{document.document_id}.candidates.json"
        target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(
            f"{target}: {len(result.candidates)} candidates, "
            f"missing={sorted(result.missing)}, needs_review={result.needs_review}"
        )
    return 0


def select_candidates(args: argparse.Namespace) -> int:
    from openparl_extractor.candidate_run import load_frozen_inputs, run_documents
    from openparl_extractor.selection_run import HttpChatClient

    config = load_llm_config()
    if not config.api_key.get_secret_value():
        print("Missing LLM_API_KEY; no calls made", file=sys.stderr)
        return 1
    if config.name != "swiss-ai/Apertus-v1.5-70B" or str(config.base_url).rstrip("/") != "https://api.inference.cscs.ch/v1":
        print("Refusing: only approved CSCS endpoint/Apertus model allowed", file=sys.stderr)
        return 1
    inputs = load_frozen_inputs()
    records = run_documents(HttpChatClient(config), config.name, inputs, args.out_dir)
    print(f"{sum(r['outcome'] == 'valid' for r in records)}/24 technically valid")
    return 0


def select_candidates_v3(args: argparse.Namespace) -> int:
    from openparl_extractor.candidate_v3_run import MODEL, load_snapshot, run_requests
    from openparl_extractor.selection_run import HttpChatClient

    config = load_llm_config()
    if not config.api_key.get_secret_value():
        print("Missing LLM_API_KEY; no calls made", file=sys.stderr)
        return 1
    if config.name != MODEL or str(config.base_url).rstrip("/") != "https://api.inference.cscs.ch/v1":
        print("Refusing: only approved CSCS endpoint/Apertus model allowed", file=sys.stderr)
        return 1
    records = run_requests(HttpChatClient(config), load_snapshot(), args.out_dir)
    print(f"{sum(r['outcome'] == 'valid' for r in records)}/12 technically valid")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="openparl-extractor")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check-config", help="validate Apertus LLM configuration")
    extract = subcommands.add_parser("extract-source", help="write SourceDocument JSON for a PDF")
    extract.add_argument("pdf", type=Path)
    extract.add_argument("--document-id", type=int, required=True)
    extract.add_argument("--affair-id", type=int)
    extract.add_argument("--out-dir", type=Path, default=Path("output/source"))
    select = subcommands.add_parser("select-fields", help="live span-id selection for title/submitters/question_or_request")
    select.add_argument("source_json", type=Path, nargs="+")
    select.add_argument("--out-dir", type=Path, default=Path("output/selection"))
    ranges = subcommands.add_parser("select-ranges", help="live local-id range selection (range-v1)")
    ranges.add_argument("source_json", type=Path, nargs="+")
    ranges.add_argument("--out-dir", type=Path, default=Path("output/selection_range_v1"))
    cands = subcommands.add_parser("generate-candidates", help="offline deterministic candidates with offsets (no model)")
    cands.add_argument("source_json", type=Path, nargs="+")
    cands.add_argument("--out-dir", type=Path, default=Path("output/candidates_v2"))
    candidate_live = subcommands.add_parser("select-candidates", help="approved Dev-only two-run candidate selection, 24 calls")
    candidate_live.add_argument("--out-dir", type=Path, default=Path("output/selection_candidates_v2_runs"))
    subcommands.add_parser("prepare-candidates-v3", help="freeze offline candidate values, contexts and v3 payloads")
    live_v3 = subcommands.add_parser("select-candidates-v3", help="one approved Dev-only pass, exactly 12 attempts")
    live_v3.add_argument("--out-dir", type=Path, default=Path("output/selection_candidates_v3"))
    subcommands.add_parser("prepare-candidates-v4", help="freeze unchanged offline v4 payloads for approved live pass")
    live_v4 = subcommands.add_parser("select-candidates-v4", help="one approved v4 Dev pass, twelve attempts")
    live_v4.add_argument("--out-dir", type=Path, default=Path("output/selection_candidates_v4"))
    args = parser.parse_args()
    if args.command == "prepare-candidates-v4":
        from openparl_extractor.candidate_v4_run import prepare_snapshot
        prepare_snapshot()
        return 0
    if args.command == "select-candidates-v4":
        from openparl_extractor.candidate_v4_run import MODEL, load_snapshot, run_requests
        from openparl_extractor.selection_run import HttpChatClient
        config = load_llm_config()
        if not config.api_key.get_secret_value():
            print("Missing LLM_API_KEY; no calls made", file=sys.stderr)
            return 1
        if config.name != MODEL or str(config.base_url).rstrip("/") != "https://api.inference.cscs.ch/v1":
            print("Refusing: only approved CSCS endpoint/Apertus model allowed", file=sys.stderr)
            return 1
        records = run_requests(HttpChatClient(config), load_snapshot(), args.out_dir)
        print(f"{sum(r['outcome'] == 'valid' for r in records)}/12 technically valid")
        return 0
    if args.command == "prepare-candidates-v3":
        from openparl_extractor.candidate_v3_run import prepare_snapshot
        prepare_snapshot()
        return 0
    if args.command == "select-candidates-v3":
        return select_candidates_v3(args)
    if args.command == "select-candidates":
        return select_candidates(args)
    if args.command == "generate-candidates":
        return generate_candidates_command(args)
    if args.command == "select-ranges":
        return select_ranges(args)
    if args.command == "select-fields":
        return select_fields(args)
    if args.command == "check-config":
        return check_config()
    if args.command == "extract-source":
        return extract_source(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
