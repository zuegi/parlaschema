import argparse
import json
from pathlib import Path

from openparl_extractor.schema import DocumentExtraction


def export_schema() -> str:
    return json.dumps(
        DocumentExtraction.model_json_schema(), ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export extraction JSON Schema v0.1")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(export_schema(), encoding="utf-8")


if __name__ == "__main__":
    main()
