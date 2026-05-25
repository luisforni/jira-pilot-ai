import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.agent import router as agent_router
from api.routes.auth import router as auth_router
from api.routes.dashboard import router as dashboard_router
from api.routes.knowledge import router as knowledge_router
from api.routes.orgs import router as orgs_router
from api.routes.pipeline import router as pipeline_router
from api.routes.webhooks import router as webhooks_router
from api.routes.ws import router as ws_router
from api.ws.subscriber import redis_subscriber
from core.config import settings

log = structlog.get_logger()

_subscriber_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _subscriber_task
    _subscriber_task = asyncio.create_task(redis_subscriber())
    log.info("startup", env=settings.app_env)
    yield
    if _subscriber_task:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except asyncio.CancelledError:
            pass
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="JiraPilot AI",
        description="Autonomous multi-agent platform that resolves Jira issues automatically",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ws_router)
    app.include_router(auth_router)
    app.include_router(orgs_router)
    app.include_router(agent_router)
    app.include_router(pipeline_router)
    app.include_router(knowledge_router)
    app.include_router(dashboard_router)
    app.include_router(webhooks_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
