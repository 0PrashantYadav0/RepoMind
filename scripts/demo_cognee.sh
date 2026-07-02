#!/usr/bin/env bash
# RepoMind demo: ingest the REAL Cognee open-source repo (code + PRs + issues)
# into COGNEE CLOUD (hosted, managed -- no self-deploy), then serve the UI.
#
# Prereqs in .env (auto-loaded):
#   COGNEE_API_KEY      - your Cognee Cloud key
#   COGNEE_SERVICE_URL  - your Cognee Cloud instance URL (https://<you>.cognee.ai)
#   GITHUB_TOKEN        - PAT (public_repo) to ingest PRs/issues/reviewers
#
# The cloud backend needs NO heavy install: no Ollama, no local model, no graph
# DB. Just httpx (already a core dependency).
#
# Usage:
#   ./scripts/demo_cognee.sh            # full ingest (all PRs/issues)
#   LITE=1 ./scripts/demo_cognee.sh     # shallow clone -> faster recording take
#   ./scripts/demo_cognee.sh 8000       # custom port
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${1:-8000}"
CONFIG="config.cognee.yaml"
CLONE_DIR=".demo/cognee"
export REPOMIND_CONFIG="$CONFIG"

export RM_ADMIN_KEY="${RM_ADMIN_KEY:-$(openssl rand -hex 32)}"
export RM_READ_KEY="${RM_READ_KEY:-$(openssl rand -hex 16)}"

echo "==> Checking prerequisites"
: "${COGNEE_API_KEY:?Set COGNEE_API_KEY in .env (your Cognee Cloud key)}"
: "${COGNEE_SERVICE_URL:?Set COGNEE_SERVICE_URL in .env (https://<you>.cognee.ai)}"
: "${GITHUB_TOKEN:?Set GITHUB_TOKEN in .env (PAT with public_repo scope)}"

echo "==> Cloning the Cognee repo into ${CLONE_DIR}"
mkdir -p .demo
if [ -d "$CLONE_DIR/.git" ]; then
  echo "    (already cloned; pulling latest)"
  git -C "$CLONE_DIR" pull --ff-only || true
elif [ "${LITE:-0}" = "1" ]; then
  git clone --depth 50 https://github.com/topoteretes/cognee.git "$CLONE_DIR"
else
  git clone https://github.com/topoteretes/cognee.git "$CLONE_DIR"
fi

echo "==> Backfilling: git history + all PRs + issues + reviewers -> Cognee Cloud"
uv run repomind --config "$CONFIG" backfill

echo
echo "==> Graph stats"
uv run repomind --config "$CONFIG" stats

echo
echo "==> API keys for this session"
echo "    admin (paste in UI):  $RM_ADMIN_KEY"
echo "    read  (read-only):    $RM_READ_KEY"
echo
echo "==> Serving http://127.0.0.1:${PORT}/  (Ctrl-C to stop)"
exec uv run repomind --config "$CONFIG" serve --port "$PORT"
