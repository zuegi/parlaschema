import json
from pathlib import Path
import subprocess
import sys

from openparl_extractor.schema import CORE_FIELDS, SCHEMA_VERSION
from openparl_extractor.schema_export import export_schema


ARTIFACT = Path(__file__).resolve().parents[1] / "schemas" / "extraction-v0.1.json"


def test_export_matches_versioned_artifact():
    assert ARTIFACT.read_bytes() == export_schema().encode("utf-8")


def test_export_is_deterministic_and_has_required_core_fields():
    assert export_schema() == export_schema()
    schema = json.loads(export_schema())
    assert set(CORE_FIELDS) <= set(schema["required"])
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert schema["additionalProperties"] is False


def test_module_export_command(tmp_path):
    output = tmp_path / "schema.json"
    subprocess.run(
        [sys.executable, "-m", "openparl_extractor.schema_export", str(output)], check=True
    )
    assert output.read_bytes() == ARTIFACT.read_bytes()
