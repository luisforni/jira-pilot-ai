from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = "change-me-in-production"

    # Jira
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "PROJ"

    # AI Providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/jira_pilot"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "jira_pilot_knowledge"

    # Git
    git_default_branch: str = "develop"
    git_author_name: str = "JiraPilot AI"
    git_author_email: str = "ai@jira-pilot.dev"

    # n8n
    n8n_webhook_secret: str = "change-me-in-production"

    # Sandbox
    sandbox_docker_image: str = "jira-pilot-sandbox:latest"
    sandbox_timeout_seconds: int = 300


settings = Settings()
