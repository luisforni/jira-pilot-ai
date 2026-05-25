from enum import Enum
from pydantic import BaseModel, Field


class TicketType(str, Enum):
    BUG = "bug"
    FEATURE = "feature"
    REFACTOR = "refactor"
    HOTFIX = "hotfix"
    TASK = "task"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RunTicketRequest(BaseModel):
    ticket_id: str = Field(..., examples=["PROJ-145"])
    title: str = Field(..., examples=["Fix login timeout"])
    description: str = Field(default="")
    labels: list[str] = Field(default_factory=list)
    repository: str = Field(..., examples=["git@github.com:company/api.git"])
    branch_base: str = Field(default="develop")
    assignee_account_id: str | None = Field(
        default=None,
        description="Jira account ID to assign the ticket after PR is created",
    )


class TicketAnalysis(BaseModel):
    type: TicketType
    files_probably_related: list[str] = Field(default_factory=list)
    risk: RiskLevel
    stack: list[str] = Field(default_factory=list)
    priority: str = "medium"
    summary: str = ""


class TechnicalPlan(BaseModel):
    steps: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    files_to_create: list[str] = Field(default_factory=list)
    estimated_complexity: str = "medium"


class PipelineStatus(str, Enum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    DEVELOPING = "developing"
    TESTING = "testing"
    REVIEWING = "reviewing"
    PR_CREATED = "pr_created"
    FAILED = "failed"
    COMPLETED = "completed"


class RunTicketResponse(BaseModel):
    task_id: str
    ticket_id: str
    status: PipelineStatus
    message: str = ""


class TaskStatusResponse(BaseModel):
    task_id: str
    ticket_id: str
    status: PipelineStatus
    pull_request_url: str | None = None
    branch_name: str | None = None
    error: str | None = None
    analysis: TicketAnalysis | None = None
    plan: TechnicalPlan | None = None
