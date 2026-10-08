import argparse
import sys

from openparl_extractor.config import ConfigError, load_llm_config
from openparl_extractor.scoped_cli import add_command, extract


def check_config() -> int:
    try:
        config = load_llm_config()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"LLM configuration valid: {config.name} at {config.base_url}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="openparl-extractor")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check-config", help="validate Apertus LLM configuration")
    add_command(subcommands)
    args = parser.parse_args()
    if args.command == "check-config":
        return check_config()
    if args.command == "extract-scope-v02":
        return extract(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
