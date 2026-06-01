#!/usr/bin/env bash

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$REPO_ROOT/logs/orchestrator.log"
PYTHON="$HOME/anaconda3/envs/kanto-heat/bin/python"

mkdir -p "$REPO_ROOT/logs"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] --- cycle start ---" >> "$LOG_FILE"
cd "$REPO_ROOT"
"$PYTHON" src/cds_orchestrator.py "$@" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] --- cycle end (exit $EXIT_CODE) ---" >> "$LOG_FILE"
exit $EXIT_CODE
