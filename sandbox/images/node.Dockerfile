FROM node:20-slim

LABEL maintainer="JiraPilot AI" \
      description="Isolated Node.js sandbox for AI-generated code validation"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install global QA tools
RUN npm install -g --silent \
    eslint@9 \
    @eslint/js \
    typescript \
    ts-node \
    vitest

# Create non-root sandbox user
RUN useradd -m -u 1000 -s /bin/bash sandbox

WORKDIR /workspace
