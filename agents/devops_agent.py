from pathlib import Path

import httpx

from agents.qa_agent import QAResult
from agents.reviewer import ReviewResult
from api.models.ticket import TicketAnalysis, TechnicalPlan
from core.config import settings
from core.git_manager import GitManager


class DevOpsAgent:
    def __init__(self, git_manager: GitManager, repo_path: Path) -> None:
        self._git = git_manager
        self._repo_path = repo_path

    def prepare_branch(self, title: str, base_branch: str = "develop") -> str:
        self._git.checkout_base(base_branch)
        branch_name = self._git.branch_name_for_ticket(title)
        self._git.create_feature_branch(branch_name)
        return branch_name

    def get_diff(self) -> str:
        import git
        repo = git.Repo(self._repo_path)
        return repo.git.diff("HEAD")

    def commit_and_push(self, ticket_id: str, title: str, branch_name: str) -> str:
        message = f"feat({ticket_id}): {title}\n\nAutomated implementation by JiraPilot AI"
        commit_sha = self._git.commit_all(message)
        self._git.push(branch_name)
        return commit_sha

    async def create_pull_request(
        self,
        github_token: str,
        repo_slug: str,
        branch_name: str,
        base_branch: str,
        ticket_id: str,
        title: str,
        analysis: TicketAnalysis,
        plan: TechnicalPlan,
        qa_result: QAResult,
        review_result: ReviewResult,
    ) -> str:
        body = self._build_pr_body(ticket_id, analysis, plan, qa_result, review_result)
        pr_title = f"feat({ticket_id}): {title}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/repos/{repo_slug}/pulls",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "title": pr_title,
                    "body": body,
                    "head": branch_name,
                    "base": base_branch,
                },
                timeout=30,
            )
            response.raise_for_status()
            return str(response.json()["html_url"])

    def _build_pr_body(
        self,
        ticket_id: str,
        analysis: TicketAnalysis,
        plan: TechnicalPlan,
        qa_result: QAResult,
        review_result: ReviewResult,
    ) -> str:
        steps = "\n".join(f"- {s}" for s in plan.steps)
        return f"""## Jira Ticket: {ticket_id}

**Type**: {analysis.type.value} | **Risk**: {analysis.risk.value} | **Priority**: {analysis.priority}

**Analysis**: {analysis.summary}

## Implementation Plan

{steps}

## QA Results

{qa_result.to_summary()}

{review_result.to_pr_comment()}

---
*Automated by [JiraPilot AI](https://github.com/luisforni/jira-pilot-ai)*
"""
