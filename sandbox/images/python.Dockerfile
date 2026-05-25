FROM python:3.11-slim

LABEL maintainer="JiraPilot AI" \
      description="Isolated Python sandbox for AI-generated code validation"

# Install system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python QA toolchain
RUN pip install --no-cache-dir \
    pytest==8.3.4 \
    pytest-asyncio==0.24.0 \
    pytest-cov==6.0.0 \
    ruff==0.7.4 \
    mypy==1.13.0 \
    bandit==1.8.0 \
    safety==3.2.9 \
    httpx==0.27.2 \
    poetry==1.8.4

# Create non-root sandbox user
RUN useradd -m -u 1000 -s /bin/bash sandbox

# No ENTRYPOINT — commands are passed at runtime
WORKDIR /workspace
