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
    args = parser.parse_args()
    if args.command == "select-fields":
        return select_fields(args)
    if args.command == "check-config":
        return check_config()
    if args.command == "extract-source":
        return extract_source(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
