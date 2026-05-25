from jira import JIRA
from core.config import settings


def get_jira_client() -> JIRA:
    return JIRA(
        server=settings.jira_url,
        basic_auth=(settings.jira_email, settings.jira_api_token),
    )


class JiraClient:
    def __init__(self) -> None:
        self._client = get_jira_client()

    def get_issue(self, issue_key: str) -> dict:
        issue = self._client.issue(issue_key)
        return {
            "key": issue.key,
            "summary": issue.fields.summary,
            "description": issue.fields.description or "",
            "status": issue.fields.status.name,
            "priority": issue.fields.priority.name if issue.fields.priority else "Medium",
            "labels": list(issue.fields.labels),
            "assignee": issue.fields.assignee.emailAddress if issue.fields.assignee else None,
            "reporter": issue.fields.reporter.emailAddress if issue.fields.reporter else None,
            "issue_type": issue.fields.issuetype.name,
        }

    def transition_issue(self, issue_key: str, status_name: str) -> None:
        transitions = self._client.transitions(issue_key)
        transition_id = next(
            (t["id"] for t in transitions if t["name"].lower() == status_name.lower()),
            None,
        )
        if transition_id:
            self._client.transition_issue(issue_key, transition_id)

    def add_comment(self, issue_key: str, body: str) -> None:
        self._client.add_comment(issue_key, body)

    def assign_issue(self, issue_key: str, account_id: str) -> None:
        self._client.assign_issue(issue_key, account_id)

    def update_label(self, issue_key: str, label: str) -> None:
        issue = self._client.issue(issue_key)
        labels = list(issue.fields.labels)
        if label not in labels:
            labels.append(label)
            issue.update(fields={"labels": labels})
