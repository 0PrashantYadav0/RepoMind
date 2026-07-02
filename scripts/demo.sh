#!/usr/bin/env bash
# RepoMind local demo runner.
#
# Boots the full end-to-end flow against the in-memory backend (no AI deps,
# no external tokens): generates API keys, ingests this repo's git history,
# prints graph stats, and starts the API + web UI.
#
# Usage:  ./scripts/demo.sh [port]
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${1:-8000}"
export REPOMIND_CONFIG="${REPOMIND_CONFIG:-config.yaml}"

# Generate ephemeral keys unless the caller already exported them.
export RM_ADMIN_KEY="${RM_ADMIN_KEY:-$(openssl rand -hex 32)}"
export RM_READ_KEY="${RM_READ_KEY:-$(openssl rand -hex 16)}"

echo "==> Ingesting git history (backfill)"
uv run repomind --config "$REPOMIND_CONFIG" backfill

echo
echo "==> Graph stats"
uv run repomind --config "$REPOMIND_CONFIG" stats

echo
echo "==> API keys for this session"
echo "    admin (full):  $RM_ADMIN_KEY"
echo "    read  (UI):    $RM_READ_KEY"
echo
echo "==> Starting server on http://127.0.0.1:${PORT}/  (Ctrl-C to stop)"
exec uv run repomind --config "$REPOMIND_CONFIG" serve --port "$PORT"
