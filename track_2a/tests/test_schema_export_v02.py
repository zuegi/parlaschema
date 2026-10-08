import json
from pathlib import Path
import subprocess
import sys

from openparl_extractor.schema import CORE_FIELDS
from openparl_extractor.schema_export import export_schema as export_v01
from openparl_extractor.schema_export_v02 import export_schema
from openparl_extractor.schema_v02 import SCHEMA_VERSION


ARTIFACT = Path(__file__).resolve().parents[1] / "schemas" / "extraction-v0.2.json"


def test_export_matches_versioned_artifact():
    assert ARTIFACT.read_bytes() == export_schema().encode("utf-8")


def test_export_is_deterministic_and_has_required_fields():
    assert export_schema() == export_schema()
    schema = json.loads(export_schema())
    assert set(CORE_FIELDS) <= set(schema["required"])
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert schema["additionalProperties"] is False
    for definition in schema["$defs"].values():
        if "properties" in definition:
            assert definition["additionalProperties"] is False
            if set(definition["properties"]) == {"value", "sources"}:
                assert set(definition["required"]) == {"value", "sources"}
            if "original" in definition["properties"]:
                assert {"original", "sources"} <= set(definition["required"])


def test_module_export_command_is_explicit_and_v01_default_unchanged(tmp_path):
    for module, expected in (("schema_export_v02", export_schema()), ("schema_export", export_v01())):
        output = tmp_path / f"{module}.json"
        subprocess.run(
            [sys.executable, "-m", f"openparl_extractor.{module}", str(output)], check=True
        )
        assert output.read_text() == expected
