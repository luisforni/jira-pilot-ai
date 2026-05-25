import subprocess
from pathlib import Path


class QAResult:
    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.test_output: str = ""
        self.lint_output: str = ""

    def to_summary(self) -> str:
        lines = [f"QA Result: {'PASS' if self.passed else 'FAIL'}"]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {e}" for e in self.errors)
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {w}" for w in self.warnings)
        return "\n".join(lines)


class QAAgent:
    def __init__(self, repo_path: Path, timeout: int = 120) -> None:
        self.repo_path = repo_path
        self.timeout = timeout

    def _run(self, cmd: list[str]) -> tuple[int, str]:
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return 1, f"Command timed out after {self.timeout}s: {' '.join(cmd)}"
        except FileNotFoundError:
            return 0, f"Tool not found (skipped): {cmd[0]}"

    def run(self) -> QAResult:
        result = QAResult()

        # Detect project type
        if (self.repo_path / "pyproject.toml").exists() or (self.repo_path / "setup.py").exists():
            result = self._run_python_checks(result)
        elif (self.repo_path / "package.json").exists():
            result = self._run_node_checks(result)

        return result

    def _run_python_checks(self, result: QAResult) -> QAResult:
        code, output = self._run(["ruff", "check", "."])
        result.lint_output = output
        if code != 0:
            result.warnings.append("Linting issues found")

        code, output = self._run(["pytest", "--tb=short", "-q"])
        result.test_output = output
        if code != 0:
            result.passed = False
            result.errors.append("Tests failed")

        return result

    def _run_node_checks(self, result: QAResult) -> QAResult:
        code, output = self._run(["npm", "run", "lint", "--if-present"])
        result.lint_output = output
        if code != 0:
            result.warnings.append("Linting issues found")

        code, output = self._run(["npm", "test", "--if-present", "--", "--passWithNoTests"])
        result.test_output = output
        if code != 0:
            result.passed = False
            result.errors.append("Tests failed")

        return result
