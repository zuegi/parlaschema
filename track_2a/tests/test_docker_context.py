from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

import pytest


ROOT = Path(__file__).parents[1]
RULES = (ROOT / ".dockerignore").read_text().splitlines()


def excluded(path: str) -> bool:
    """Static check of our **/basename-only rules, not a general Docker matcher."""
    ignored = False
    for rule in RULES:
        include = rule.startswith("!")
        pattern = rule.removeprefix("!")
        assert pattern.startswith("**/") and "/" not in pattern[3:]
        if any(fnmatchcase(part, pattern[3:]) for part in PurePosixPath(path).parts):
            ignored = not include
    return ignored


@pytest.mark.parametrize("path", [
    "output/run/result.json", "nested/output/reference-draft.json",
    "data/input.pdf", "src/nested/source.PDF", "nested/input.PdF",
    ".env", ".env.local", "nested/.env.production", "src/.env",
    ".venv/lib/package.py", "nested/venv/bin/python",
    "private/reference-draft.json", "nested/private_pdf_review/reference-draft.json",
    "private_schema_feasibility/dev-schema-atlas.json",
    "raw/response.json", "data/raw_metadata/api.json",
    ".git/config", ".aws/credentials", ".ssh/id_rsa", ".copilot/state.json",
    ".secrets/token", "nested/.netrc", ".pypirc", "nested/secrets/token", "credentials.json",
    "nested/server.pem", "nested/server.key", "config.local.json", "settings.local.env",
    "model.gguf", "weights.safetensors", "checkpoint.ckpt", "model.pt", "weights.bin",
    "__pycache__/module.pyc", "nested/.pytest_cache/state", "nested/module.pyo",
    "node_modules/package/index.js", "dist/app.js", "build/package.whl",
    ".DS_Store", ".idea/workspace.xml", ".vscode/settings.json",
])
def test_private_artifact_patterns_at_root_and_nested_depth(path):
    assert excluded(path)


@pytest.mark.parametrize("path", [
    "pyproject.toml", "uv.lock", "README.md", "Dockerfile", ".dockerignore",
    "src/openparl_extractor/cli.py", "src/openparl_extractor/schema.py",
    ".env.example", "nested/.env.example",
    "data/manifest.json", "data/pdf-inspection.json",
    "tests/test_schema.py", "tests/fixtures/synthetic-reference.json",
    "tests/fixtures/synthetic.source.json", "schemas/extraction-v0.1.json",
    "docs/schema.md", "docs/feasibility.md",
])
def test_public_synthetic_and_startup_paths_not_blanket_excluded(path):
    assert not excluded(path)


def test_current_docker_copy_inputs_remain_available():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY pyproject.toml uv.lock README.md ./" in dockerfile
    assert "COPY src ./src" in dockerfile
    for path in ("pyproject.toml", "uv.lock", "README.md"):
        assert (ROOT / path).is_file() and not excluded(path)
    for path in (ROOT / "src").rglob("*.py"):
        assert not excluded(path.relative_to(ROOT).as_posix())
    assert 'CMD ["check-config"]' in dockerfile


def test_compose_and_ci_use_reviewed_track_context():
    assert "    build: .\n" in (ROOT / "docker-compose.yml").read_text()
    ci = (ROOT.parent / ".github/workflows/ci.yml").read_text()
    assert "working-directory: track_2a" in ci
    assert "docker build -t openparl-extractor:ci ." in ci
