import asyncio
import os

import structlog

from agents.developer import DeveloperAgent
from agents.devops_agent import DevOpsAgent
from agents.planner import PlannerAgent
from agents.qa_agent import QAAgent
from agents.repository_analyzer import RepositoryAnalyzerAgent
from agents.reviewer import ReviewerAgent
from agents.ticket_analyzer import TicketAnalyzerAgent
from api.models.ticket import PipelineStatus
from core.git_manager import GitManager
from core.jira_client import JiraClient
from workers.celery_app import celery_app

log = structlog.get_logger()


def _update_jira_status(jira: JiraClient, ticket_id: str, status: str, comment: str = "") -> None:
    try:
        jira.transition_issue(ticket_id, status)
        if comment:
            jira.add_comment(ticket_id, comment)
    except Exception as exc:
        log.warning("jira_update_failed", ticket_id=ticket_id, error=str(exc))


async def _run_pipeline(
    task_id: str,
    ticket_id: str,
    title: str,
    description: str,
    labels: list[str],
    repository: str,
    branch_base: str,
    github_token: str,
    repo_slug: str,
    assignee_account_id: str | None,
) -> dict:
    jira = JiraClient()
    git_manager = GitManager(repository, ticket_id)

    try:
        _update_jira_status(jira, ticket_id, "AI_ANALYZING", "🤖 JiraPilot AI is analyzing this ticket.")

        analyzer = TicketAnalyzerAgent()
        analysis = await analyzer.analyze(ticket_id, title, description, labels)
        log.info("ticket_analyzed", ticket_id=ticket_id, type=analysis.type.value)

        repo_path = git_manager.clone()
        devops = DevOpsAgent(git_manager, repo_path)
        branch_name = devops.prepare_branch(title, branch_base)
        log.info("branch_created", branch=branch_name)

        repo_analyzer = RepositoryAnalyzerAgent()
        repo_context = await repo_analyzer.analyze(repo_path, analysis)

        _update_jira_status(jira, ticket_id, "AI_DEVELOPING")

        planner = PlannerAgent()
        plan = await planner.plan(analysis, repo_context, title, description)
        log.info("plan_created", steps=len(plan.steps))

        developer = DeveloperAgent()
        modified_files = await developer.implement(repo_path, plan, analysis, repo_context, title, description)
        log.info("implementation_done", files=modified_files)

        _update_jira_status(jira, ticket_id, "AI_TESTING")

        qa = QAAgent(repo_path)
        qa_result = qa.run()
        log.info("qa_done", passed=qa_result.passed)

        diff = devops.get_diff()
        reviewer = ReviewerAgent()
        review_result = await reviewer.review(plan, modified_files, qa_result, diff)
        log.info("review_done", approved=review_result.approved)

        commit_sha = devops.commit_and_push(ticket_id, title, branch_name)
        log.info("pushed", sha=commit_sha)

        pr_url = await devops.create_pull_request(
            github_token, repo_slug, branch_name, branch_base,
            ticket_id, title, analysis, plan, qa_result, review_result,
        )
        log.info("pr_created", url=pr_url)

        _update_jira_status(
            jira,
            ticket_id,
            "PR_CREATED",
            f"✅ PR created by JiraPilot AI: {pr_url}\n\n{review_result.to_pr_comment()}",
        )

        if assignee_account_id:
            jira.assign_issue(ticket_id, assignee_account_id)

        return {
            "status": PipelineStatus.PR_CREATED.value,
            "pull_request_url": pr_url,
            "branch_name": branch_name,
            "analysis": analysis.model_dump(),
            "plan": plan.model_dump(),
        }

    except Exception as exc:
        log.error("pipeline_failed", ticket_id=ticket_id, error=str(exc))
        _update_jira_status(jira, ticket_id, "FAILED", f"❌ JiraPilot AI pipeline failed: {exc}")
        return {"status": PipelineStatus.FAILED.value, "error": str(exc)}
    finally:
        git_manager.cleanup()


@celery_app.task(bind=True, name="workers.tasks.run_ticket_pipeline")
def run_ticket_pipeline(self, **kwargs) -> dict:
    return asyncio.get_event_loop().run_until_complete(_run_pipeline(self.request.id, **kwargs))
