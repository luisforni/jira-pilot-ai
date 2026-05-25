#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Building JiraPilot AI sandbox images..."

docker build \
  -f "$SCRIPT_DIR/python.Dockerfile" \
  -t jira-pilot-sandbox-python:latest \
  "$SCRIPT_DIR"

echo "✓ jira-pilot-sandbox-python:latest"

docker build \
  -f "$SCRIPT_DIR/node.Dockerfile" \
  -t jira-pilot-sandbox-node:latest \
  "$SCRIPT_DIR"

echo "✓ jira-pilot-sandbox-node:latest"
echo "Done. Sandbox images ready."
