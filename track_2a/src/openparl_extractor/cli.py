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


def main() -> int:
    parser = argparse.ArgumentParser(prog="openparl-extractor")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check-config", help="validate Apertus LLM configuration")
    extract = subcommands.add_parser("extract-source", help="write SourceDocument JSON for a PDF")
    extract.add_argument("pdf", type=Path)
    extract.add_argument("--document-id", type=int, required=True)
    extract.add_argument("--affair-id", type=int)
    extract.add_argument("--out-dir", type=Path, default=Path("output/source"))
    args = parser.parse_args()
    if args.command == "check-config":
        return check_config()
    if args.command == "extract-source":
        return extract_source(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
