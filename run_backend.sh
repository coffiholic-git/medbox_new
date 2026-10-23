#!/usr/bin/env bash
# Launcher for the MedBox backend. Safe to run from anywhere.
#
# Why: backend/ modules use absolute imports like "from backend.database
# import init_db", which only resolve when the process is started from
# THIS directory (project/), the parent of backend/. Running
# "cd backend && uvicorn main:app" instead fails with:
#   ModuleNotFoundError: No module named 'backend'
#
# This script cd's to the right place for you before starting uvicorn.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "Note: ANTHROPIC_API_KEY is not set - the AI voice assistant will" >&2
  echo "reply with a 'not configured yet' message until you:" >&2
  echo "  export ANTHROPIC_API_KEY=sk-ant-..." >&2
fi

exec uvicorn backend.main:app --reload "$@"
