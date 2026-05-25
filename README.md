# JiraPilot AI

Autonomous multi-agent platform that analyzes Jira tickets, implements solutions, runs QA, and opens pull requests automatically.

## Architecture

```
Jira Webhook
    ↓
n8n (orchestrator)
    ↓
JiraPilot API (FastAPI)
    ↓
Celery Worker
    ↓
┌─────────────────────────────────────┐
│         Multi-Agent Pipeline        │
│                                     │
│  1. Ticket Analyzer                 │
│  2. Repository Analyzer             │
│  3. Planner                         │
│  4. Developer Agent                 │
│  5. QA Agent                        │
│  6. Reviewer Agent                  │
│  7. DevOps Agent                    │
└─────────────────────────────────────┘
    ↓
Git Branch feat/* + Pull Request
    ↓
Jira Status Update
```

## Jira Workflow States

```
OPEN → AI_ANALYZING → AI_DEVELOPING → AI_TESTING → PR_CREATED → HUMAN_REVIEW → DONE
```

## Trigger Labels

Add any of these labels to a Jira ticket to trigger the pipeline:

- `ai:auto-fix` — automatic bug fix
- `ai:backend` — backend feature/fix
- `ai:frontend` — frontend feature/fix
- `ai:hotfix` — high-priority fix

## Quick Start

```bash
cp .env.example .env
# Edit .env with your credentials

docker compose up -d
```

API available at `http://localhost:8000`
n8n available at `http://localhost:5678`

## Manual Trigger

```bash
curl -X POST http://localhost:8000/agent/run-ticket \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: your-secret" \
  -d '{
    "ticket_id": "PROJ-145",
    "title": "Fix login timeout",
    "description": "Users experience 30s timeout on login endpoint",
    "labels": ["bug", "backend"],
    "repository": "git@github.com:company/api.git",
    "branch_base": "develop"
  }'
```

## Development

```bash
poetry install
poetry run uvicorn api.main:app --reload
poetry run celery -A workers.celery_app worker -Q pipeline --loglevel=info
poetry run pytest
```

## Stack

- **API**: FastAPI + Uvicorn
- **Workers**: Celery + Redis
- **AI**: LangGraph + Anthropic Claude / OpenAI
- **Vector Store**: Qdrant
- **Database**: PostgreSQL
- **Orchestration**: n8n
- **Git**: GitPython
