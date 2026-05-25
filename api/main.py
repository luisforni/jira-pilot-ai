from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.agent import router as agent_router
from api.routes.knowledge import router as knowledge_router
from api.routes.pipeline import router as pipeline_router
from api.routes.webhooks import router as webhooks_router
from core.config import settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("startup", env=settings.app_env)
    yield
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

    app.include_router(agent_router)
    app.include_router(pipeline_router)
    app.include_router(knowledge_router)
    app.include_router(webhooks_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
