from pathlib import Path

import structlog

from core.sandbox.detector import detect_stack
from core.sandbox.runner import SandboxResult, SandboxRunner

log = structlog.get_logger()


class QAResult:
    def __init__(self, sandbox_result: SandboxResult) -> None:
        self._result = sandbox_result
        self.passed = sandbox_result.passed
        self.errors: list[str] = [
            f"{' '.join(r.command)}: exit {r.exit_code}" + (" (timeout)" if r.timed_out else "")
            for r in sandbox_result.commands
            if not r.passed
        ]
        self.warnings: list[str] = []
        self.test_output = "\n".join(
            r.stdout for r in sandbox_result.commands if r.stdout
        )
        self.lint_output = ""
        self.total_duration_ms = sandbox_result.total_duration_ms
        self.fallback_used = sandbox_result.fallback_used

    def to_summary(self) -> str:
        return self._result.to_summary()


class QAAgent:
    def __init__(
        self,
        repo_path: Path,
        timeout: int = 120,
        mem_limit: str = "512m",
    ) -> None:
        self.repo_path = repo_path
        self._runner = SandboxRunner(timeout=timeout, mem_limit=mem_limit)

    def run(self) -> QAResult:
        stack = detect_stack(self.repo_path)
        log.info("qa_stack_detected", language=stack.language, image=stack.image)

        if not self._runner.available:
            log.warning("docker_unavailable_using_fallback")
            return self._subprocess_fallback(stack)

        if not self._runner.image_exists(stack.image):
            log.warning("sandbox_image_missing", image=stack.image)
            return self._subprocess_fallback(stack)

        main_commands = stack.lint_commands + stack.test_commands
        result = self._runner.run_pipeline(
            image=stack.image,
            repo_path=self.repo_path,
            setup_commands=stack.setup_commands,
            main_commands=main_commands,
        )

        log.info(
            "qa_sandbox_done",
            passed=result.passed,
            total_ms=result.total_duration_ms,
            commands=len(result.commands),
        )
        return QAResult(result)

    def _subprocess_fallback(self, stack) -> QAResult:
        import subprocess
        import time
        from core.sandbox.runner import CommandResult, SandboxResult

        results: list[CommandResult] = []
        all_passed = True

        for cmd in stack.lint_commands + stack.test_commands:
            t0 = time.monotonic()
            timed_out = False
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                exit_code = proc.returncode
                stdout = proc.stdout
                stderr = proc.stderr
            except subprocess.TimeoutExpired:
                exit_code = 1
                stdout = ""
                stderr = "Timed out"
                timed_out = True
            except FileNotFoundError:
                exit_code = 0
                stdout = f"Skipped (tool not found): {cmd[0]}"
                stderr = ""

            ms = int((time.monotonic() - t0) * 1000)
            r = CommandResult(command=cmd, exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=ms, timed_out=timed_out)
            results.append(r)
            if not r.passed:
                all_passed = False

        total_ms = sum(r.duration_ms for r in results)
        sandbox_result = SandboxResult(passed=all_passed, commands=results, total_duration_ms=total_ms, fallback_used=True)
        return QAResult(sandbox_result)
