"""Sanity checks for repository / CI consistency.

These tests are cheap and do not need network access. They guard against
common packaging/CI drift (version mismatch, missing workflow files, etc.).
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_package_version_matches_pyproject():
    """__init__.__version__ must equal pyproject.toml project.version."""
    init_file = PROJECT_ROOT / "__init__.py"
    pyproject_file = PROJECT_ROOT / "pyproject.toml"

    assert init_file.exists(), "missing __init__.py"
    assert pyproject_file.exists(), "missing pyproject.toml"

    init_ns = {}
    exec(_read_text(init_file), init_ns)  # noqa: S102
    init_version = init_ns.get("__version__")
    assert init_version, "__version__ not defined in __init__.py"

    pyproject_text = _read_text(pyproject_file)
    # Extract `version = "x.y.z"` from [project] table.
    version_line = next(
        (line for line in pyproject_text.splitlines() if line.strip().startswith("version ")),
        None,
    )
    assert version_line, "version not found in pyproject.toml [project]"
    pyproject_version = version_line.split("=", 1)[1].strip().strip('"')

    assert init_version == pyproject_version, (
        f"version mismatch: __init__.py={init_version!r}, "
        f"pyproject.toml={pyproject_version!r}"
    )


def test_ci_workflow_exists_and_is_valid_yaml():
    """.github/workflows/ci.yml must exist and be valid YAML."""
    yaml = pytest.importorskip("yaml")
    ci_file = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_file.exists(), "missing .github/workflows/ci.yml"
    data = yaml.safe_load(_read_text(ci_file))
    assert isinstance(data, dict)
    assert data.get("name") == "CI"
    assert "jobs" in data


def test_requirements_files_present_and_non_empty():
    """requirements.txt and requirements-dev.txt must exist and have content."""
    for name in ("requirements.txt", "requirements-dev.txt"):
        req_file = PROJECT_ROOT / name
        assert req_file.exists(), f"missing {name}"
        text = _read_text(req_file)
        non_comment_lines = [
            line for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert non_comment_lines, f"{name} has no real dependency lines"


def test_requirements_bazi_file_present_and_non_empty():
    """requirements-bazi.txt must exist and have content (cached by CI)."""
    req_file = PROJECT_ROOT / "requirements-bazi.txt"
    assert req_file.exists(), "missing requirements-bazi.txt"
    text = _read_text(req_file)
    non_comment_lines = [
        line for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert non_comment_lines, "requirements-bazi.txt has no real dependency lines"


def test_dockerfile_exists():
    """Dockerfile must exist for the docker CI job to be meaningful."""
    dockerfile = PROJECT_ROOT / "Dockerfile"
    assert dockerfile.exists(), "missing Dockerfile"
    assert "FROM" in _read_text(dockerfile)


def test_server_routes_are_registered(tmp_path: Path):
    """server/app.py should register the expected REST endpoints."""
    pytest.importorskip("fastapi")

    from fastapi.testclient import TestClient

    from config import ConfigLoader
    from server.app import build_app

    config_path = tmp_path / "config.yml"
    download_path = tmp_path / "Downloaded"
    config_path.write_text(
        f"path: {download_path}\n"
        "mode: [post]\n"
        "link: []\n"
        "thread: 5\n"
        "rate_limit: 2\n"
        "retry_times: 3\n",
        encoding="utf-8",
    )
    config = ConfigLoader(str(config_path))
    app = build_app(config)

    registered = {route.path for route in app.routes if hasattr(route, "path")}
    expected = {
        "/api/v1/health",
        "/api/v1/download",
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}",
        "/api/v1/jobs/{job_id}/events",
        "/api/v1/config",
        "/api/v1/bazi/analyze",
        "/api/v1/bazi/cases",
        "/api/v1/bazi/extract",
        "/api/v1/bazi/feedback",
    }
    for path in expected:
        assert path in registered, f"missing route {path}"

    # Smoke-test the health endpoint without starting a real server.
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
