from pathlib import Path


class ProjectStack:
    def __init__(
        self,
        language: str,
        image: str,
        setup_commands: list[list[str]],
        test_commands: list[list[str]],
        lint_commands: list[list[str]],
    ) -> None:
        self.language = language
        self.image = image
        self.setup_commands = setup_commands
        self.test_commands = test_commands
        self.lint_commands = lint_commands


_PYTHON_IMAGE = "jira-pilot-sandbox-python:latest"
_NODE_IMAGE = "jira-pilot-sandbox-node:latest"


def detect_stack(repo_path: Path) -> ProjectStack:
    if (repo_path / "pyproject.toml").exists():
        has_poetry = "poetry" in (repo_path / "pyproject.toml").read_text(errors="ignore")
        setup = [["poetry", "install", "--no-interaction"]] if has_poetry else [["pip", "install", "-e", ".[dev]", "--quiet"]]
        return ProjectStack(
            language="python",
            image=_PYTHON_IMAGE,
            setup_commands=setup,
            test_commands=[["pytest", "--tb=short", "-q", "--no-header"]],
            lint_commands=[["ruff", "check", "."]],
        )

    if (repo_path / "requirements.txt").exists():
        return ProjectStack(
            language="python",
            image=_PYTHON_IMAGE,
            setup_commands=[["pip", "install", "-r", "requirements.txt", "--quiet"]],
            test_commands=[["pytest", "--tb=short", "-q", "--no-header"]],
            lint_commands=[["ruff", "check", "."]],
        )

    if (repo_path / "setup.py").exists():
        return ProjectStack(
            language="python",
            image=_PYTHON_IMAGE,
            setup_commands=[["pip", "install", "-e", ".", "--quiet"]],
            test_commands=[["pytest", "--tb=short", "-q", "--no-header"]],
            lint_commands=[["ruff", "check", "."]],
        )

    if (repo_path / "package.json").exists():
        pkg = (repo_path / "package.json").read_text(errors="ignore")
        manager = "yarn" if (repo_path / "yarn.lock").exists() else "npm"
        install_cmd = [manager, "install", "--silent"] if manager == "npm" else ["yarn", "install", "--silent"]
        test_cmd = [manager, "test", "--", "--passWithNoTests", "--watchAll=false"]
        lint_cmd = [manager, "run", "lint", "--if-present"] if manager == "npm" else ["yarn", "lint"]
        return ProjectStack(
            language="node",
            image=_NODE_IMAGE,
            setup_commands=[install_cmd],
            test_commands=[test_cmd],
            lint_commands=[lint_cmd],
        )

    # Fallback: Python image, just lint with ruff
    return ProjectStack(
        language="unknown",
        image=_PYTHON_IMAGE,
        setup_commands=[],
        test_commands=[],
        lint_commands=[["ruff", "check", "."]],
    )
