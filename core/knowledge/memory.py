import hashlib

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge.graph import KnowledgeGraph
from core.knowledge.models import EdgeRelation, NodeType

log = structlog.get_logger()


def project_id_from_repo(repository: str) -> str:
    return hashlib.md5(repository.encode()).hexdigest()[:16]


class ProjectMemory:
    """High-level interface to query accumulated project knowledge before a pipeline run."""

    def __init__(self, session: AsyncSession, project_id: str) -> None:
        self._graph = KnowledgeGraph(session, project_id)
        self._project_id = project_id

    async def get_context_for_ticket(
        self,
        ticket_type: str,
        files_hint: list[str],
        title: str,
    ) -> str:
        similar_fixes = await self._graph.get_similar_fixes(ticket_type, files_hint)
        file_contexts: dict[str, dict] = {}
        for file_path in files_hint[:5]:
            ctx = await self._graph.get_file_context(file_path)
            if any(ctx.values()):
                file_contexts[file_path] = ctx

        patterns = await self._graph.list_nodes(NodeType.PATTERN)
        services = await self._graph.list_nodes(NodeType.SERVICE)

        if not similar_fixes and not file_contexts and not patterns:
            return ""

        sections: list[str] = ["## Project Memory (accumulated knowledge)\n"]

        if similar_fixes:
            sections.append("### Similar past fixes")
            for fix in similar_fixes:
                props = fix.properties
                sections.append(
                    f"- **{props.get('ticket_id', '?')}** ({props.get('ticket_type', '?')}): "
                    f"{fix.description} — changed: {', '.join(props.get('files_changed', []))}"
                )
            sections.append("")

        if file_contexts:
            sections.append("### Known file relationships")
            for path, ctx in file_contexts.items():
                if ctx["dependencies"]:
                    sections.append(f"- `{path}` depends on: {', '.join(ctx['dependencies'])}")
                if ctx["services"]:
                    sections.append(f"- `{path}` belongs to: {', '.join(ctx['services'])}")
                if ctx["patterns"]:
                    sections.append(f"- `{path}` uses patterns: {', '.join(ctx['patterns'])}")
            sections.append("")

        if services:
            sections.append("### Project services")
            for svc in services[:10]:
                stack = ", ".join(svc.properties.get("stack", []))
                sections.append(f"- **{svc.label}**: {svc.description}" + (f" [{stack}]" if stack else ""))
            sections.append("")

        if patterns:
            sections.append("### Established patterns")
            for pat in patterns[:8]:
                sections.append(f"- **{pat.label}**: {pat.description}")
            sections.append("")

        memory_text = "\n".join(sections)
        log.info(
            "project_memory_loaded",
            project_id=self._project_id,
            fixes=len(similar_fixes),
            files=len(file_contexts),
            patterns=len(patterns),
        )
        return memory_text
