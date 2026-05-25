import asyncio
import time

import structlog

from agents.developer import DeveloperAgent
from agents.devops_agent import DevOpsAgent
from agents.planner import PlannerAgent
from agents.qa_agent import QAAgent
from agents.repository_analyzer import RepositoryAnalyzerAgent
from agents.reviewer import ReviewerAgent
from agents.ticket_analyzer import TicketAnalyzerAgent
from api.models.ticket import PipelineStatus
from core.database import AsyncSessionLocal
from core.git_manager import GitManager
from core.jira_client import JiraClient
from core.events import publish
from core.knowledge.extractor import KnowledgeExtractor
from core.knowledge.memory import ProjectMemory, project_id_from_repo
from core.repositories import PipelineRunRepository
from workers.celery_app import celery_app

log = structlog.get_logger()


def _update_jira(jira: JiraClient, ticket_id: str, status: str, comment: str = "") -> None:
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
    repo_analyzer: RepositoryAnalyzerAgent | None = None
    project_id = project_id_from_repo(repository)

    async with AsyncSessionLocal() as session:
        run_repo = PipelineRunRepository(session)
        run = await run_repo.create(
            celery_task_id=task_id,
            ticket_id=ticket_id,
            title=title,
            description=description,
            labels=labels,
            repository=repository,
            branch_base=branch_base,
        )
        run_id = run.id
        await session.commit()

    async def _record(agent: str, status: str, output: dict | None = None, error: str | None = None, ms: int = 0) -> None:
        async with AsyncSessionLocal() as s:
            r = PipelineRunRepository(s)
            await r.add_agent_result(run_id, agent, status, output, error, ms)
            await s.commit()
        await publish("agent_done", task_id=task_id, ticket_id=ticket_id, agent=agent, status=status, duration_ms=ms)

    async def _set_status(status: str, **kwargs) -> None:
        async with AsyncSessionLocal() as s:
            r = PipelineRunRepository(s)
            await r.update_status(run_id, status, **kwargs)
            await s.commit()
        await publish("pipeline_status", task_id=task_id, ticket_id=ticket_id, status=status, **{
            k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool, type(None)))
        })

    try:
        _update_jira(jira, ticket_id, "AI_ANALYZING", "🤖 JiraPilot AI is analyzing this ticket.")
        await _set_status(PipelineStatus.ANALYZING.value)

        t0 = time.monotonic()
        analyzer = TicketAnalyzerAgent()
        analysis = await analyzer.analyze(ticket_id, title, description, labels)
        ms = int((time.monotonic() - t0) * 1000)
        await _record("ticket_analyzer", "success", analysis.model_dump(), ms=ms)
        log.info("ticket_analyzed", ticket_id=ticket_id, type=analysis.type.value)

        repo_path = git_manager.clone()
        devops = DevOpsAgent(git_manager, repo_path)
        branch_name = devops.prepare_branch(title, branch_base)
        await _set_status(PipelineStatus.PLANNING.value, branch_name=branch_name)

        # Load project memory (previous knowledge about this repo)
        t0 = time.monotonic()
        async with AsyncSessionLocal() as s:
            memory = ProjectMemory(s, project_id)
            project_memory = await memory.get_context_for_ticket(
                ticket_type=analysis.type.value,
                files_hint=analysis.files_probably_related,
                title=title,
            )
        ms = int((time.monotonic() - t0) * 1000)
        await _record("project_memory", "success", {"chars": len(project_memory)}, ms=ms)
        log.info("project_memory_loaded", project_id=project_id, chars=len(project_memory))

        t0 = time.monotonic()
        repo_analyzer = RepositoryAnalyzerAgent()
        repo_context = await repo_analyzer.analyze(repo_path, analysis)
        ms = int((time.monotonic() - t0) * 1000)
        await _record("repository_analyzer", "success", {"chars": len(repo_context)}, ms=ms)

        t0 = time.monotonic()
        planner = PlannerAgent()
        plan = await planner.plan(analysis, repo_context, title, description, project_memory=project_memory)
        ms = int((time.monotonic() - t0) * 1000)
        await _record("planner", "success", plan.model_dump(), ms=ms)
        log.info("plan_created", steps=len(plan.steps))

        _update_jira(jira, ticket_id, "AI_DEVELOPING")
        await _set_status(PipelineStatus.DEVELOPING.value)

        t0 = time.monotonic()
        developer = DeveloperAgent()
        modified_files = await developer.implement(repo_path, plan, analysis, repo_context, title, description)
        ms = int((time.monotonic() - t0) * 1000)
        await _record("developer", "success", {"files": modified_files}, ms=ms)

        _update_jira(jira, ticket_id, "AI_TESTING")
        await _set_status(PipelineStatus.TESTING.value)

        t0 = time.monotonic()
        qa = QAAgent(repo_path)
        qa_result = qa.run()
        ms = int((time.monotonic() - t0) * 1000)
        await _record(
            "qa_agent",
            "success" if qa_result.passed else "warning",
            {"passed": qa_result.passed, "errors": qa_result.errors},
            ms=ms,
        )

        t0 = time.monotonic()
        diff = devops.get_diff()
        reviewer = ReviewerAgent()
        review_result = await reviewer.review(plan, modified_files, qa_result, diff)
        ms = int((time.monotonic() - t0) * 1000)
        await _record(
            "reviewer",
            "success" if review_result.approved else "warning",
            {"approved": review_result.approved, "issues": review_result.blocking_issues},
            ms=ms,
        )
        await _set_status(PipelineStatus.REVIEWING.value)

        commit_sha = devops.commit_and_push(ticket_id, title, branch_name)

        t0 = time.monotonic()
        pr_url = await devops.create_pull_request(
            github_token, repo_slug, branch_name, branch_base,
            ticket_id, title, analysis, plan, qa_result, review_result,
        )
        ms = int((time.monotonic() - t0) * 1000)
        await _record("devops_agent", "success", {"pr_url": pr_url, "sha": commit_sha}, ms=ms)
        log.info("pr_created", url=pr_url)

        # Extract and store knowledge for future runs
        try:
            async with AsyncSessionLocal() as s:
                extractor = KnowledgeExtractor()
                await extractor.extract_and_store(
                    session=s,
                    project_id=project_id,
                    ticket_id=ticket_id,
                    analysis=analysis,
                    plan=plan,
                    modified_files=modified_files,
                    repo_context=repo_context,
                    pr_url=pr_url,
                )
        except Exception as exc:
            log.warning("knowledge_extraction_failed", error=str(exc))

        _update_jira(
            jira, ticket_id, "PR_CREATED",
            f"✅ PR created by JiraPilot AI: {pr_url}\n\n{review_result.to_pr_comment()}",
        )

        if assignee_account_id:
            jira.assign_issue(ticket_id, assignee_account_id)

        await _set_status(
            PipelineStatus.PR_CREATED.value,
            pull_request_url=pr_url,
            analysis=analysis.model_dump(),
            plan=plan.model_dump(),
        )

        return {
            "status": PipelineStatus.PR_CREATED.value,
            "pull_request_url": pr_url,
            "branch_name": branch_name,
            "analysis": analysis.model_dump(),
            "plan": plan.model_dump(),
        }

    except Exception as exc:
        log.error("pipeline_failed", ticket_id=ticket_id, error=str(exc))
        _update_jira(jira, ticket_id, "FAILED", f"❌ JiraPilot AI pipeline failed: {exc}")
        await _set_status(PipelineStatus.FAILED.value, error=str(exc))
        return {"status": PipelineStatus.FAILED.value, "error": str(exc)}

    finally:
        if repo_analyzer:
            try:
                await repo_analyzer.cleanup_index(repo_path)
            except Exception:
                pass
        git_manager.cleanup()


@celery_app.task(bind=True, name="workers.tasks.run_ticket_pipeline")
def run_ticket_pipeline(self, **kwargs) -> dict:
    return asyncio.get_event_loop().run_until_complete(_run_pipeline(self.request.id, **kwargs))
