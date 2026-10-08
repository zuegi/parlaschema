import base64
import json
import math
import sys
from pathlib import Path

from pydantic import ValidationError

from openparl_extractor.config import ConfigError, load_llm_config
from openparl_extractor.scoped_contract import SourceDocument
from openparl_extractor.scoped_pipeline import (
    CONTROL_MAX_TOKENS, DEFAULT_MAX_TOKENS, DEFAULT_TIMEOUT, extract_control, extract_scope,
)


EXIT_BY_STATE = {"accepted": 0, "partial": 3, "failed": 1}
USAGE_ERROR = 2
OUTPUT_ERROR = 4


def add_command(subcommands) -> None:
    parser = subcommands.add_parser("extract-scope-v02", help="explicit two-task v0.2 scope")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, help="private raw responses, base64-encoded")
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--control", action="store_true", help="one-request control; default 8192 tokens")


def write_output(path: Path, content: str) -> bool:
    try:
        path.write_text(content, encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"Cannot write {path}: {error}", file=sys.stderr)
        return False
    return True


def load_input(path: Path) -> SourceDocument:
    try:
        return SourceDocument.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as error:
        raise ValueError("Input does not match the page-based source schema") from error


def extract(args) -> int:
    try:
        if args.max_tokens is None:
            args.max_tokens = CONTROL_MAX_TOKENS if args.control else DEFAULT_MAX_TOKENS
        if args.max_tokens <= 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("max_tokens and timeout must be positive and finite")
        if args.raw_output and args.raw_output.resolve() == args.output.resolve():
            raise ValueError("raw-output and output must be different paths")
        if args.input.resolve() in [path.resolve() for path in (args.output, args.raw_output)
                                    if path is not None]:
            raise ValueError("output paths must not overwrite input")
        source, config = load_input(args.input), load_llm_config()
    except (OSError, UnicodeError, ValueError, ConfigError) as error:
        print(f"Cannot start scoped extraction: {error}", file=sys.stderr)
        return USAGE_ERROR
    return run_and_write(args, source, config)


def run_and_write(args, source, config) -> int:
    print("Scope only: answers/decisions unprocessed. Source text sent to configured endpoint; "
          "use only authorized inputs. Raw responses remain private.", file=sys.stderr)
    raw: dict[str, str] = {}
    result = (extract_control if args.control else extract_scope)(
        source, config, args.max_tokens, args.timeout,
        on_response=lambda name, payload: raw.update({name: base64.b64encode(payload).decode("ascii")}),
    )
    result_ok = write_output(args.output, result.model_dump_json(indent=2) + "\n")
    raw_ok = True
    if args.raw_output:
        raw_ok = write_output(args.raw_output, json.dumps({"encoding": "base64", "responses": raw},
                                                        indent=2) + "\n")
    for name in ("metadata", "questions"):
        task = getattr(result, name)
        if task.error:
            print(f"{name}: {task.error.code}: {task.error.message}", file=sys.stderr)
    if result_ok:
        print(f"scope {result.state}: {args.output}", file=sys.stderr)
    return EXIT_BY_STATE[result.state] if result_ok and raw_ok else OUTPUT_ERROR
