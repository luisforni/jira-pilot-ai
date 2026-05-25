import os
import tempfile
from pathlib import Path

import git
from core.config import settings


class GitManager:
    def __init__(self, repo_url: str, ticket_key: str) -> None:
        self.repo_url = repo_url
        self.ticket_key = ticket_key
        self._work_dir: str | None = None
        self._repo: git.Repo | None = None

    def clone(self) -> Path:
        self._work_dir = tempfile.mkdtemp(prefix=f"jira-pilot-{self.ticket_key}-")
        self._repo = git.Repo.clone_from(self.repo_url, self._work_dir)
        self._repo.config_writer().set_value("user", "name", settings.git_author_name).release()
        self._repo.config_writer().set_value("user", "email", settings.git_author_email).release()
        return Path(self._work_dir)

    def checkout_base(self, base_branch: str = "develop") -> None:
        assert self._repo is not None
        origin = self._repo.remotes.origin
        origin.fetch()
        self._repo.git.checkout(f"origin/{base_branch}", "-b", base_branch)

    def create_feature_branch(self, branch_name: str) -> str:
        assert self._repo is not None
        self._repo.git.checkout("-b", branch_name)
        return branch_name

    def commit_all(self, message: str) -> str:
        assert self._repo is not None
        self._repo.git.add("-A")
        commit = self._repo.index.commit(message)
        return commit.hexsha

    def push(self, branch_name: str) -> None:
        assert self._repo is not None
        origin = self._repo.remotes.origin
        origin.push(refspec=f"{branch_name}:{branch_name}")

    def cleanup(self) -> None:
        if self._work_dir and os.path.exists(self._work_dir):
            import shutil
            shutil.rmtree(self._work_dir, ignore_errors=True)

    def branch_name_for_ticket(self, summary: str) -> str:
        slug = summary.lower().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")[:50]
        return f"feat/{self.ticket_key.lower()}-{slug}"
