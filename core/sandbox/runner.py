import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger()

# Commands allowed inside the sandbox
_ALLOWED_EXECUTABLES = {
    "pytest", "python", "python3", "ruff", "mypy", "bandit", "safety",
    "npm", "npx", "node", "yarn", "eslint", "jest", "vitest",
    "pip", "pip3", "poetry", "cargo", "go", "mvn", "gradle",
    "sh", "bash",
}

# Env vars that must never leak into the sandbox
_SECRET_PATTERNS = re.compile(
    r"(key|secret|token|password|passwd|pwd|credential|auth|private)",
    re.IGNORECASE,
)

_SANDBOX_USER = "1000:1000"
_DEFAULT_MEM_LIMIT = "512m"
_DEFAULT_CPU_QUOTA = 50_000   # 50% of one core
_DEFAULT_CPU_PERIOD = 100_000


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class SandboxResult:
    passed: bool
    commands: list[CommandResult] = field(default_factory=list)
    total_duration_ms: int = 0
    fallback_used: bool = False

    def to_summary(self) -> str:
        lines = [f"Sandbox: {'PASS' if self.passed else 'FAIL'}" +
                 (" (subprocess fallback)" if self.fallback_used else "")]
        for r in self.commands:
            status = "✓" if r.passed else ("⏱" if r.timed_out else "✗")
            lines.append(f"  {status} {' '.join(r.command)} ({r.duration_ms}ms)")
            if not r.passed and r.stderr:
                lines.append(f"    {r.stderr[:300]}")
        return "\n".join(lines)


def _validate_command(cmd: list[str]) -> None:
    if not cmd:
        raise ValueError("Empty command")
    exe = Path(cmd[0]).name
    if exe not in _ALLOWED_EXECUTABLES:
        raise ValueError(f"Command not allowed in sandbox: {exe!r}")


def _scrub_env(env: dict) -> dict:
    return {k: v for k, v in env.items() if not _SECRET_PATTERNS.search(k)}


class SandboxRunner:
    def __init__(
        self,
        timeout: int = 120,
        mem_limit: str = _DEFAULT_MEM_LIMIT,
        cpu_quota: int = _DEFAULT_CPU_QUOTA,
    ) -> None:
        self._timeout = timeout
        self._mem_limit = mem_limit
        self._cpu_quota = cpu_quota
        self._client = self._init_client()

    def _init_client(self):
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return client
        except Exception as exc:
            log.warning("docker_unavailable", error=str(exc))
            return None

    @property
    def available(self) -> bool:
        return self._client is not None

    def run_command(
        self,
        image: str,
        command: list[str],
        repo_path: Path,
        network_enabled: bool = False,
        extra_env: dict | None = None,
    ) -> CommandResult:
        _validate_command(command)

        if self._client is None:
            return self._subprocess_fallback(command, repo_path)

        env = _scrub_env(extra_env or {})
        container = None
        t0 = time.monotonic()

        try:
            container = self._client.containers.run(
                image=image,
                command=command,
                volumes={str(repo_path.resolve()): {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                network_mode="bridge" if network_enabled else "none",
                mem_limit=self._mem_limit,
                cpu_period=_DEFAULT_CPU_PERIOD,
                cpu_quota=self._cpu_quota,
                user=_SANDBOX_USER,
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                environment=env,
                remove=False,
                detach=True,
                stdout=True,
                stderr=True,
            )

            timed_out = False
            try:
                result = container.wait(timeout=self._timeout)
                exit_code = result.get("StatusCode", 1)
            except Exception:
                container.kill()
                exit_code = 1
                timed_out = True

            raw_logs = container.logs(stdout=True, stderr=True)
            output = raw_logs.decode(errors="replace") if raw_logs else ""
            stdout, _, stderr = output.partition("\n---stderr---\n")

            duration_ms = int((time.monotonic() - t0) * 1000)
            log.info(
                "sandbox_command_done",
                command=command[0],
                exit_code=exit_code,
                duration_ms=duration_ms,
                timed_out=timed_out,
            )
            return CommandResult(
                command=command,
                exit_code=exit_code,
                stdout=output,
                stderr="",
                duration_ms=duration_ms,
                timed_out=timed_out,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            log.error("sandbox_run_failed", command=command, error=str(exc))
            return CommandResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_ms=duration_ms,
            )
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def run_pipeline(
        self,
        image: str,
        repo_path: Path,
        setup_commands: list[list[str]],
        main_commands: list[list[str]],
    ) -> SandboxResult:
        """
        Two-phase execution:
        1. setup_commands  — network enabled (install deps)
        2. main_commands   — network disabled (tests + lint)
        """
        results: list[CommandResult] = []
        total_start = time.monotonic()

        # Phase 1: setup (network on, allowed to install deps)
        for cmd in setup_commands:
            try:
                _validate_command(cmd)
            except ValueError:
                continue
            r = self.run_command(image, cmd, repo_path, network_enabled=True)
            results.append(r)
            if not r.passed:
                log.warning("sandbox_setup_failed", command=cmd, exit_code=r.exit_code)
                # Don't abort — tests might still work without full setup

        # Phase 2: tests + lint (network off)
        all_passed = True
        for cmd in main_commands:
            try:
                _validate_command(cmd)
            except ValueError:
                continue
            r = self.run_command(image, cmd, repo_path, network_enabled=False)
            results.append(r)
            if not r.passed:
                all_passed = False

        total_ms = int((time.monotonic() - total_start) * 1000)
        return SandboxResult(passed=all_passed, commands=results, total_duration_ms=total_ms)

    def _subprocess_fallback(self, command: list[str], repo_path: Path) -> CommandResult:
        import subprocess
        t0 = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env={},  # clean env
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            exit_code = 1
            stdout = ""
            stderr = f"Timed out after {self._timeout}s"
            timed_out = True
        except Exception as exc:
            exit_code = 1
            stdout = ""
            stderr = str(exc)
        return CommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.monotonic() - t0) * 1000),
            timed_out=timed_out,
        )

    def image_exists(self, image: str) -> bool:
        if not self._client:
            return False
        try:
            self._client.images.get(image)
            return True
        except Exception:
            return False
