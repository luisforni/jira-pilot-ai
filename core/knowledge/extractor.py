import json

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.ticket import TicketAnalysis, TechnicalPlan
from core.config import settings
from core.knowledge.graph import KnowledgeGraph
from core.knowledge.models import EdgeRelation, NodeType

log = structlog.get_logger()

_SYSTEM_PROMPT = """You are a software architect extracting structured knowledge from a completed development pipeline.

Given the ticket analysis, plan, modified files, and repo context, extract knowledge as JSON:

{
  "files": [
    {
      "path": "relative/path/to/file.py",
      "description": "what this file does",
      "language": "python",
      "belongs_to_service": "ServiceName or null",
      "depends_on": ["other/file.py"]
    }
  ],
  "services": [
    {
      "name": "ServiceName",
      "description": "what this service does",
      "stack": ["python", "fastapi"]
    }
  ],
  "patterns": [
    {
      "name": "PatternName",
      "description": "short description of the pattern",
      "used_in_files": ["path/to/file.py"]
    }
  ],
  "fix_summary": "one sentence describing what was done and why it worked"
}

Focus only on files that were actually modified or are closely related. Be concise.
"""


class KnowledgeExtractor:
    def __init__(self) -> None:
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2048,
        )

    async def extract_and_store(
        self,
        session: AsyncSession,
        project_id: str,
        ticket_id: str,
        analysis: TicketAnalysis,
        plan: TechnicalPlan,
        modified_files: list[str],
        repo_context: str,
        pr_url: str,
    ) -> None:
        graph = KnowledgeGraph(session, project_id)

        prompt = f"""Ticket: {ticket_id} ({analysis.type.value})
Summary: {analysis.summary}
Files modified: {modified_files}
Plan steps: {plan.steps}

Repository context (excerpt):
{repo_context[:4000]}

Extract structured knowledge from this pipeline run."""

        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = await self._llm.ainvoke(messages)
        raw = str(response.content).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("knowledge_extraction_parse_failed", ticket_id=ticket_id)
            return

        service_nodes: dict[str, any] = {}
        for svc in data.get("services", []):
            node = await graph.get_or_create_node(
                NodeType.SERVICE,
                label=svc["name"],
                description=svc.get("description", ""),
                properties={"stack": svc.get("stack", [])},
            )
            service_nodes[svc["name"]] = node

        pattern_nodes: dict[str, any] = {}
        for pat in data.get("patterns", []):
            node = await graph.get_or_create_node(
                NodeType.PATTERN,
                label=pat["name"],
                description=pat.get("description", ""),
            )
            pattern_nodes[pat["name"]] = node

        file_nodes: dict[str, any] = {}
        for f in data.get("files", []):
            node = await graph.get_or_create_node(
                NodeType.FILE,
                label=f["path"],
                description=f.get("description", ""),
                properties={"language": f.get("language", "")},
            )
            file_nodes[f["path"]] = node

            if svc_name := f.get("belongs_to_service"):
                if svc_node := service_nodes.get(svc_name):
                    await graph.add_edge(node, svc_node, EdgeRelation.BELONGS_TO)

        for pat_name, pat_node in pattern_nodes.items():
            pat_data = next((p for p in data.get("patterns", []) if p["name"] == pat_name), {})
            for used_in in pat_data.get("used_in_files", []):
                if file_node := file_nodes.get(used_in):
                    await graph.add_edge(file_node, pat_node, EdgeRelation.USES_PATTERN)

        for f in data.get("files", []):
            if file_node := file_nodes.get(f["path"]):
                for dep_path in f.get("depends_on", []):
                    dep_node = await graph.get_or_create_node(NodeType.FILE, label=dep_path)
                    await graph.add_edge(file_node, dep_node, EdgeRelation.DEPENDS_ON)

        fix_label = f"{ticket_id}: {analysis.summary[:80]}"
        fix_node = await graph.get_or_create_node(
            NodeType.FIX,
            label=fix_label,
            description=data.get("fix_summary", ""),
            properties={
                "ticket_id": ticket_id,
                "ticket_type": analysis.type.value,
                "risk": analysis.risk.value,
                "files_changed": modified_files,
                "pr_url": pr_url,
            },
        )

        for file_node in file_nodes.values():
            await graph.add_edge(fix_node, file_node, EdgeRelation.FIXED_BY)

        await session.commit()
        log.info(
            "knowledge_extracted",
            ticket_id=ticket_id,
            files=len(file_nodes),
            services=len(service_nodes),
            patterns=len(pattern_nodes),
        )
