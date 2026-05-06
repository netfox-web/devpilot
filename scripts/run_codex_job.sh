#!/bin/sh
set -eu

JOB_ID="${1:-}"
PROJECT_ID="${2:-}"
WORKTREE_PATH="${3:-}"
TASK_PROMPT="${4:-}"

if [ -z "$JOB_ID" ] || [ -z "$PROJECT_ID" ] || [ -z "$WORKTREE_PATH" ]; then
  echo "usage: run_codex_job.sh job_id project_id worktree_path task_prompt" >&2
  exit 64
fi

case "$WORKTREE_PATH" in
  /volume1/worktrees/*) ;;
  *)
    echo "refused: worktree_path must be under /volume1/worktrees" >&2
    exit 65
    ;;
esac

if [ ! -d "$WORKTREE_PATH" ]; then
  echo "refused: worktree_path does not exist: $WORKTREE_PATH" >&2
  exit 66
fi

cd "$WORKTREE_PATH"
RESOLVED_WORKTREE="$(pwd -P)"

case "$RESOLVED_WORKTREE" in
  /volume1/worktrees/*) ;;
  *)
    echo "refused: resolved worktree escaped /volume1/worktrees: $RESOLVED_WORKTREE" >&2
    exit 67
    ;;
esac

cat > .devpilot_external_runner_test.txt <<EOF
external codex runner mock
job_id=$JOB_ID
project_id=$PROJECT_ID
timestamp=$(date '+%Y-%m-%d %H:%M:%S %Z')
worktree=$RESOLVED_WORKTREE
task=$TASK_PROMPT
EOF

echo "external runner mock wrote $RESOLVED_WORKTREE/.devpilot_external_runner_test.txt"

if command -v codex >/dev/null 2>&1; then
  echo "codex CLI detected, but this runner script is currently in mock mode"
else
  echo "codex CLI not installed on this execution environment"
fi
