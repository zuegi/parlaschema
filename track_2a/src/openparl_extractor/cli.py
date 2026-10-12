import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from openparl_extractor.block_classification import (
    DEFAULT_CONTRACT, DEFAULT_METHOD, ClassificationParseError, unique_object,
)
from openparl_extractor.block_evaluation import ReplayDataset, evaluate_replay
from openparl_extractor.block_live import exploratory_command
from openparl_extractor.config import ConfigError, load_llm_config


def check_config() -> int:
    try:
        config = load_llm_config()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"LLM configuration valid: {config.name} at {config.base_url}")
    return 0


def evaluate_blocks(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        dataset = ReplayDataset.model_validate(data)
    except (OSError, UnicodeError, ValidationError) as error:
        detail = str(error) if not isinstance(error, ValidationError) else "invalid replay dataset"
        if isinstance(error, ValidationError):
            locations = [".".join(map(str, item["loc"])) for item in error.errors()]
            detail += ": " + ", ".join(locations)
        print(f"Block evaluation input error: {detail}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, ClassificationParseError):
        print("Block evaluation input error: malformed or duplicate-key JSON", file=sys.stderr)
        return 1
    print(json.dumps(evaluate_replay(dataset), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="openparl-extractor")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check-config", help="validate Apertus LLM configuration")
    offline = subcommands.add_parser("evaluate-blocks", help="evaluate offline responses; no model calls")
    offline.add_argument("dataset", type=Path)
    add_exploratory_parser(subcommands)
    args = parser.parse_args()
    if args.command == "check-config":
        return check_config()
    if args.command == "evaluate-blocks":
        return evaluate_blocks(args.dataset)
    if args.command == "prepare-block-test":
        return run_exploratory(args)
    return 2


def add_exploratory_parser(subcommands) -> None:
    runner = subcommands.add_parser("prepare-block-test", help="private exploratory dry-run by default")
    runner.add_argument("--manifest", type=Path, required=True)
    runner.add_argument("--labels", type=Path, required=True)
    runner.add_argument("--output", type=Path, required=True, help="new private directory outside checkout")
    runner.add_argument("--approval", type=Path)
    runner.add_argument("--allow-network", action="store_true", help="requires explicit bound budget approval")
    runner.add_argument("--output-contract", choices=("category-json-v0.1", "category-word-v0.1"),
                        default=DEFAULT_CONTRACT, help="explicit output contract; no autodetection")
    runner.add_argument("--method", choices=("legacy-v0.1", "source-function-v0.2"),
                        default=DEFAULT_METHOD, help="explicit semantic/input method; no fallback")


def run_exploratory(args) -> int:
    try:
        return exploratory_command(args)
    except (OSError, ValueError, KeyError, TypeError):
        print("Exploratory input/config/approval or private output error; no automatic retry.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
