import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("target,forwarded", [
    ("run", []),
    ("check-config", ["-e", "LLM_NAME", "-e", "LLM_BASE_URL", "-e", "LLM_API_KEY"]),
])
def test_make_targets_isolate_dotenv_and_forward_config_only_explicitly(tmp_path, target, forwarded):
    make = shutil.which("make")
    if make is None:
        pytest.skip("make not installed")
    docker = tmp_path / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "print(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    docker.chmod(0o700)
    result = subprocess.run(
        [make, "--no-print-directory", "-s", target], cwd=ROOT,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", "")},
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == [
        "compose", "--env-file", "/dev/null", "run", "--build", "--rm",
        *forwarded, "app", *(["check-config"] if target == "check-config" else []),
    ]


def test_docker_demo_uses_the_public_synthetic_fixture_only():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    fixture = "tests/fixtures/block-replay-synthetic.json"
    assert f"COPY {fixture} ./{fixture}" in dockerfile
    assert f'CMD ["evaluate-blocks", "{fixture}"]' in dockerfile
    assert "COPY tests " not in dockerfile
    dataset = json.loads((ROOT / fixture).read_text(encoding="utf-8"))
    assert dataset["label_status"] == "synthetic"
    assert len(dataset["cases"]) == 3
