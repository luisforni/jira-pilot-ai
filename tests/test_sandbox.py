import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.sandbox.detector import detect_stack
from core.sandbox.runner import CommandResult, SandboxResult, SandboxRunner, _scrub_env, _validate_command


# ── Command validation ────────────────────────────────────────────────────────

def test_validate_allowed_commands():
    _validate_command(["pytest", "--tb=short"])
    _validate_command(["ruff", "check", "."])
    _validate_command(["npm", "test"])


def test_validate_rejects_dangerous_commands():
    with pytest.raises(ValueError):
        _validate_command(["rm", "-rf", "/"])
    with pytest.raises(ValueError):
        _validate_command(["curl", "https://evil.com"])
    with pytest.raises(ValueError):
        _validate_command(["wget", "http://exfil.example.com"])


def test_validate_rejects_empty_command():
    with pytest.raises(ValueError):
        _validate_command([])


# ── Secret scrubbing ──────────────────────────────────────────────────────────

def test_scrub_env_removes_secrets():
    env = {
        "DATABASE_URL": "postgres://...",
        "OPENAI_API_KEY": "sk-...",
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "SECRET_KEY": "super-secret",
        "GITHUB_TOKEN": "ghp_...",
        "APP_HOST": "0.0.0.0",
        "APP_PORT": "8000",
    }
    scrubbed = _scrub_env(env)
    assert "OPENAI_API_KEY" not in scrubbed
    assert "ANTHROPIC_API_KEY" not in scrubbed
    assert "SECRET_KEY" not in scrubbed
    assert "GITHUB_TOKEN" not in scrubbed
    # non-secret vars are kept
    assert scrubbed.get("APP_HOST") == "0.0.0.0"
    assert scrubbed.get("APP_PORT") == "8000"


# ── Stack detection ───────────────────────────────────────────────────────────

def test_detect_python_pyproject():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        (p / "pyproject.toml").write_text('[tool.poetry]\nname = "test"\n')
        stack = detect_stack(p)
    assert stack.language == "python"
    assert "pytest" in stack.test_commands[0]


def test_detect_python_requirements():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        (p / "requirements.txt").write_text("fastapi\n")
        stack = detect_stack(p)
    assert stack.language == "python"


def test_detect_node_package_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        (p / "package.json").write_text('{"name": "test", "scripts": {"test": "jest"}}')
        stack = detect_stack(p)
    assert stack.language == "node"
    assert "npm" in stack.setup_commands[0]


def test_detect_unknown_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        stack = detect_stack(Path(tmpdir))
    assert stack.language == "unknown"


# ── SandboxRunner (subprocess fallback) ──────────────────────────────────────

def test_subprocess_fallback_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        (p / "test_hello.py").write_text("def test_ok(): assert True\n")
        (p / "pyproject.toml").write_text('[tool.poetry]\nname="t"\n')

        runner = SandboxRunner(timeout=30)
        # Force fallback
        with patch.object(runner, "_client", None):
            stack = detect_stack(p)
            result = runner._subprocess_fallback(["ruff", "check", "."], p)

    # ruff may not be installed in test env — just verify structure
    assert isinstance(result, CommandResult)
    assert result.command == ["ruff", "check", "."]


def test_sandbox_result_summary():
    r1 = CommandResult(command=["ruff", "check", "."], exit_code=0, stdout="", stderr="", duration_ms=150)
    r2 = CommandResult(command=["pytest", "-q"], exit_code=1, stdout="", stderr="1 failed", duration_ms=300)
    result = SandboxResult(passed=False, commands=[r1, r2], total_duration_ms=450)
    summary = result.to_summary()
    assert "FAIL" in summary
    assert "ruff" in summary
    assert "pytest" in summary


def test_sandbox_runner_unavailable_without_docker():
    with patch("core.sandbox.runner.SandboxRunner._init_client", return_value=None):
        runner = SandboxRunner()
    assert not runner.available


def test_image_exists_returns_false_when_no_docker():
    runner = SandboxRunner.__new__(SandboxRunner)
    runner._client = None
    runner._timeout = 120
    runner._mem_limit = "512m"
    runner._cpu_quota = 50_000
    assert not runner.image_exists("any-image:latest")
