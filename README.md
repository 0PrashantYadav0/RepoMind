# RepoMind

Give a Git repository a brain.

RepoMind turns a code repository into a typed **knowledge graph** of commits,
pull requests, issues, people, decisions, and chat discussions, then lets you
ask natural-language questions whose answers come from **multi-hop graph
traversal** (e.g. `file -> commit -> pull_request -> reviewer -> issue`).
Memory is powered by [Cognee](https://github.com/topoteretes/cognee), an
open-source hybrid graph + vector memory layer.

This repository is **Phase 1**: the Git Brain.

## Why it is different from plain vector RAG

Plain RAG retrieves textually similar chunks and hopes the answer is inside.
RepoMind walks typed relationships, so it can answer questions like:

- "Why was the auth layer built this way, and who decided it?"
- "Which PR introduced this retry logic, who reviewed it, and what issue
  motivated it?"
- "What did `auth.py` do before it was deleted, and which PR removed it?"

The answer is the traversal path itself, which makes it explainable.

## Architecture (Phase 1)

```
 Sources (one Source interface, fetch() -> [Document])
   GitSource (GitPython)  GitHubSource (PyGithub)  DiscordExportSource (JSON)
              \                 |                      /
               v                v                     v
                  +------------------------------------+
                  |  Ingestor (ONE idempotent path:    |
                  |  upsert + resolve + park/retry     |
                  |  + tombstone)                      |
                  +--------------+---------------------+
                                 |
                                 v
                      +------------------------------+
                      |  GraphStore                  |
                      |  InMemoryGraphStore (default)|
                      |  CogneeMemoryStore (real)    |
                      +--------------+---------------+
                                 ^
                                 |
        +------------------------+------------------------+
        | Triggers (all funnel into the Ingestor):        |
        |  - Webhook receiver (FastAPI, HMAC-verified)    |
        |  - Optional poller (config-driven interval)     |
        |  - Manual sync  (POST /sync  +  `repomind sync`)|
        +-------------------------------------------------+

 Query: recall() entry points -> graph traversal -> answer + subgraph for viz
```

## Correctness-first design

Accuracy is prioritized over speed. Guarantees:

- **Idempotent upserts** keyed by deterministic stable IDs: re-processing the
  same entity (via webhook, poller, or sync) is an update, never a duplicate.
- **No silent loss**: the worker retries with backoff and dead-letters jobs that
  exhaust retries; they are listable and replayable, never dropped.
- **Deterministic reference resolution**: numeric issue/PR references are never
  guessed; if the target is absent they are parked and resolved once it arrives.
- **History-preserving deletion (tombstones)**: a deleted file/issue is marked
  `status=deleted` (with `deleted_in`) but keeps its content and history, so
  RepoMind can still explain what it was. True erasure (`forget()`) is reserved
  for privacy/secret/junk cases only.
- **Verify / reconcile**: a full sync re-reads the source of truth, adds what is
  missing, and tombstones what vanished upstream; `verify` reports consistency.

## Install

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"        # offline core + tests
uv pip install -e ".[dev,cognee]" # add the real Cognee Cloud backend
```

## Configure

```bash
cp config.example.yaml config.yaml
# edit repo.name and repo.local_path
```

Secrets are read from the environment and auto-loaded from a local `.env` file
(gitignored). Real environment variables always win, so CI/containers stay in
control.

```bash
# .env  (or export in your shell)
GITHUB_TOKEN=ghp_...                 # for PR/issue ingestion
REPOMIND_WEBHOOK_SECRET=...          # to verify webhooks
REPOMIND_API_TOKEN=...               # admin API key to run the server
# hosted AI backend (optional):
COGNEE_API_KEY=...                   # + set memory.backend: cognee_cloud
COGNEE_SERVICE_URL=https://<you>.cognee.ai
```

Large repo? Bound the ingest with `ingest.max_commits` / `max_prs` /
`max_issues` (0 = unlimited) to keep demos fast and stay within GitHub rate
limits.

## Use

```bash
# Ingest git history + GitHub PRs/issues
repomind --config config.yaml backfill

# Ingest an exported Discord chat (DiscordChatExporter JSON)
repomind --config config.yaml discord export.json

# Ask a question (prints the answer + the traversal that produced it)
repomind --config config.yaml ask "Who reviewed the login fix and what issue did it close?"

# Force a re-sync; full mode reconciles against the source of truth
repomind --config config.yaml sync --scope all --full

# Verify the graph matches the source of truth (exit code 1 if inconsistent)
repomind --config config.yaml verify

# Show graph counts
repomind --config config.yaml stats

# Run the API (webhook receiver + /ask + /graph + /sync + /verify)
repomind --config config.yaml serve
```

### HTTP API

| Method |    Path    |                      Purpose                         |
|--------|------------|------------------------------------------------------|
| GET    | `/livez`   | unauthenticated liveness probe (no data)             |
| GET    | `/health`  | liveness + counts (requires API key)                 |
| POST   | `/ask`     | `{question, limit}` -> answer + traversal + subgraph |
| GET    | `/graph`   | full node/edge data for visualization                |
| POST   | `/sync`    | `{scope, mode}` manual sync (mode: incremental/full) |
| POST   | `/verify`  | `{scope}` reconcile + consistency report             |
| POST   | `/forget`  | `{target}` hard erase (privacy/secret/junk)          |
| POST   | `/ingest/message` | live chat / n8n low-code message ingest (Phase 2) |
| POST   | `/webhook` | GitHub webhook receiver (HMAC verified)              |

### Web UI

RepoMind ships a GitHub-themed web UI served by the API itself. Start the server
and open the root URL (it redirects to `/ui/`):

```bash
export REPOMIND_CONFIG=config.yaml
export RM_READ_KEY=...   # the env vars your api.keys point at
uv run repomind --config config.yaml serve --port 8000
# open http://127.0.0.1:8000/
```

Paste an API key (top-right) and click **Connect**. Tabs: **Ask** (question ->
a structured answer report with entity highlighting, grounded-on sources, and a
numbered traversal, plus a live force-graph of the path), **Graph Explorer**
(the full graph, colored by node type, with a show-tombstoned toggle), **Ingest**
(post a chat message, write scope), **Admin** (sync/verify + forget). Every graph
has zoom (`+` / `-`), **Fit**, and **fullscreen** controls. The key is
stored only in the browser's localStorage and sent as `X-API-Key`; the static
assets are unauthenticated (and served `no-cache`) but every data call requires a
valid key.

### Security

- **Every endpoint requires an API key** (except `/livez` and static UI assets).
  Supply it as
  `X-API-Key: <token>` or `Authorization: Bearer <token>`.
- **Per-client named keys with scopes** (`read` < `write` < `admin`):
  - `read`  -> `/health`, `/ask`, `/graph`
  - `write` -> `/ingest/message`, `/sync`, `/verify` (implies read)
  - `admin` -> `/forget` (implies everything)
  Define keys in `api.keys[]`; each key's secret comes from its own env var. The
  legacy single `REPOMIND_API_TOKEN` still works as an admin key named `default`.
- **Per-key rate limiting**: set `api.rate_limit` / `api.rate_window`; exceeding
  it returns **429** with a `Retry-After` header.
- **Fail-closed**: with no active keys the server returns **503**. Unknown/invalid
  key -> **401**; valid key without the needed scope -> **403**.
- `/livez` is an unauthenticated liveness probe that returns no data.
- **Webhooks** are exempt from the API key (GitHub can't send one) but are
  fail-closed via HMAC (`webhook.require_signature: true`, set
  `REPOMIND_WEBHOOK_SECRET`).

```bash
export REPOMIND_API_TOKEN=$(openssl rand -hex 32)   # admin key, required to serve
curl -H "X-API-Key: $REPOMIND_API_TOKEN" http://127.0.0.1:8000/health
```

See `docs/SECURITY_REVIEW.md` for the full self-review.

## Testing

The entire pipeline is tested **offline** against the in-memory store with a
throwaway git repo and fake GitHub objects -- no network or API keys required.

```bash
uv run pytest
```

## Real backend: Cognee

Two AI-backed options, both keep the exact typed graph locally for
traversal/path-highlighting and delegate hybrid vector+graph recall to Cognee:

- **`memory.backend: cognee_cloud`** (hosted, zero self-hosting) -- set
  `COGNEE_API_KEY` and `COGNEE_SERVICE_URL`. Nothing to install or deploy
  beyond `httpx`: no local model, no Ollama, no graph DB. Node text is pushed to
  your hosted instance (`add` + `cognify`) and questions run against it
  (`search`); everything else runs server-side.
- **`memory.backend: cognee`** (in-process SDK) -- runs Cognee locally with a
  local LLM + embeddings (Ollama) and an embedded kuzu graph. Fully offline but
  heavier. See `docs/LOCAL_COGNEE.md`.

Either way the structural graph is identical to the offline backend, so behavior
and tests transfer directly.

## Phase 2: live connectors (implemented)

All three live paths share the same `Source` interface and idempotent pipeline:

- **Live Slack bot** (`SlackBotSource`): paginated `conversations.history`
  backfill + Events API live tail. Install: `pip install -e ".[slack]"`.
- **Live Discord bot** (`DiscordBotSource`): gateway `channel.history` backfill
  + `on_message` live tail. Install: `pip install -e ".[discord]"`.
- **n8n low-code lane** (Option C): POST normalized messages to
  `/ingest/message`, no backend code. See `integrations/n8n/README.md`.

Messages from every path become the same `Message` nodes, with `#123` references
linked to issues/PRs as `discussed-in` edges (chat <-> code bridge).
