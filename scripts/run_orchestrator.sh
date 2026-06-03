#!/usr/bin/env bash

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$REPO_ROOT/logs/orchestrator.log"
LOCK_FILE="$REPO_ROOT/logs/orchestrator.lock"
PYTHON="$HOME/anaconda3/envs/kanto-heat/bin/python"

mkdir -p "$REPO_ROOT/logs"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] --- cycle skipped (already running) ---"
    exit 0
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] --- cycle start ---" >> "$LOG_FILE"
cd "$REPO_ROOT"
"$PYTHON" src/cds_orchestrator.py "$@" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] --- cycle end (exit $EXIT_CODE) ---" >> "$LOG_FILE"
exit $EXIT_CODE
