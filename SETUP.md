# RepoMind Setup Guide

Run RepoMind locally on your own repository with your own tokens.

There are two ways to run it:

- **Fast path (in-memory backend)** — no AI dependencies, instant, great for
  validating the flow. Uses deterministic keyword search + graph traversal.
- **Local AI path (Cognee + Ollama)** — fully self-hosted hybrid graph+vector
  recall, no cloud, no API keys. Slower (runs a local LLM), more powerful.

Start with the fast path, then switch to the local AI path if you want it.

---

## 1. Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv)
- `git`
- A **local clone** of the repository you want to ingest
- A **GitHub Personal Access Token (PAT)** with read access to that repo
  - Public repo: `public_repo` scope
  - Private repo: `repo` scope

```bash
# clone the repo you want RepoMind to learn (anywhere on disk)
git clone https://github.com/<owner>/<name>.git ~/code/<name>
```

---

## 2. Install

```bash
cd repomind
uv venv --python 3.11
uv pip install -e ".[dev]"          # core + tests (in-memory backend, no AI)
```

Optional extras (install later as needed):

```bash
uv pip install -e ".[cognee]"       # local AI backend (Cognee)
uv pip install -e ".[slack]"        # live Slack bot (Phase 2)
uv pip install -e ".[discord]"      # live Discord bot (Phase 2)
```

---

## 3. Generate your secrets

Secrets live in environment variables, never in the config file. The config only
references the env var *names*.

```bash
export RM_ADMIN_KEY=$(openssl rand -hex 32)             # full access (admin)
export RM_READ_KEY=$(openssl rand -hex 16)              # read-only (UI/dashboards)
export GITHUB_TOKEN=ghp_your_real_token_here           # your GitHub PAT
export REPOMIND_WEBHOOK_SECRET=$(openssl rand -hex 16)  # only if using live webhooks
```

To make these permanent, add them to your shell profile (`~/.zshrc` /
`~/.bashrc`) or use a `.env` file you keep out of git.

---

## 4. Create `config.yaml`

Copy `config.example.yaml` to `config.yaml` and edit. Minimal version for the
fast path:

```yaml
repo:
  name: "<owner>/<name>"                 # e.g. "acme/api" -- used for GitHub API + node IDs
  local_path: "/Users/you/code/<name>"   # your local clone
  github_token_env: "GITHUB_TOKEN"

memory:
  backend: "memory"                      # fast, no AI (switch to "cognee" in section 9)
  persist_path: "graph.json"             # graph survives restarts

state:
  db_path: "repomind_state.sqlite3"

api:
  rate_limit: 0                          # set e.g. 100 to throttle per key (per window)
  rate_window: "1m"
  keys:
    - name: ops
      token_env: RM_ADMIN_KEY
      scopes: [admin]
    - name: dashboard
      token_env: RM_READ_KEY
      scopes: [read]

webhook:
  enabled: true
  require_signature: true                # requires REPOMIND_WEBHOOK_SECRET

polling:
  enabled: false                         # optional auto-refresh (section 10)
  interval: "15m"
```

---

## 5. Ingest your repository

```bash
export REPOMIND_CONFIG=config.yaml
uv run repomind --config config.yaml backfill   # git history + PRs/issues/reviewers
uv run repomind --config config.yaml stats       # node/edge counts
```

Optional -- add chat context. Export a Discord channel with
[DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) to JSON:

```bash
uv run repomind --config config.yaml discord ./export.json
```

---

## 6. Ask from the CLI

```bash
uv run repomind --config config.yaml ask "Why was the auth layer built this way and who reviewed it?"
```

It prints the answer plus the traversal path that produced it.

---

## 7. Run the server and open the web UI

```bash
uv run repomind --config config.yaml serve --port 8000
# open http://127.0.0.1:8000/   (redirects to the UI)
```

In the UI:

1. Paste an API key (top-right) -- `$RM_ADMIN_KEY` for everything, or
   `$RM_READ_KEY` for read-only -- and click **Connect**.
2. **Ask** tab: natural-language questions -> answer + traversal + a live graph.
3. **Graph Explorer**: browse the full knowledge graph (toggle tombstoned nodes).
4. **Ingest**: post a chat message (needs write/admin scope).
5. **Admin**: sync / verify / forget (needs write/admin scope).

---

## 8. Call the HTTP API directly (optional)

Every endpoint needs your key via `X-API-Key` or `Authorization: Bearer`.

```bash
# read
curl -H "X-API-Key: $RM_READ_KEY" http://127.0.0.1:8000/health
curl -H "X-API-Key: $RM_READ_KEY" -H 'Content-Type: application/json' \
     -d '{"question":"who owns the payments module"}' http://127.0.0.1:8000/ask
curl -H "X-API-Key: $RM_READ_KEY" http://127.0.0.1:8000/graph

# write
curl -H "X-API-Key: $RM_ADMIN_KEY" -H 'Content-Type: application/json' \
     -d '{"scope":"all","mode":"full"}' http://127.0.0.1:8000/sync

# admin (hard-erase a node by stable id)
curl -H "X-API-Key: $RM_ADMIN_KEY" -H 'Content-Type: application/json' \
     -d '{"target":"git:file:<owner>/<name>:secret.py"}' http://127.0.0.1:8000/forget
```

| Method | Path | Scope |
|---|---|---|
| GET | `/livez` | none (liveness) |
| GET | `/health`, `/graph` ; POST `/ask` | read |
| POST | `/ingest/message`, `/sync`, `/verify` | write |
| POST | `/forget` | admin |
| POST | `/webhook` | GitHub HMAC (no key) |

---

## 9a. (Optional) Hosted AI with Cognee Cloud -- zero self-hosting

The easiest AI backend: no local model, no Ollama, no graph DB. Just point
RepoMind at your hosted Cognee instance.

1. Add two values to `.env` (auto-loaded):

   ```bash
   COGNEE_API_KEY=your_cognee_cloud_key
   COGNEE_SERVICE_URL=https://<your-instance>.cognee.ai
   ```

2. In `config.yaml`, set:

   ```yaml
   memory:
     backend: "cognee_cloud"
     dataset: "repomind"
     persist_path: "graph.json"
     cloud_search_type: "CHUNKS"
   ```

3. Run as usual -- ingestion pushes node text to your instance (`add` +
   `cognify`) and `ask` queries it (`search`):

   ```bash
   uv run repomind --config config.yaml backfill
   uv run repomind --config config.yaml ask "Who owns the auth module and why?"
   uv run repomind --config config.yaml serve --port 8000
   ```

Nothing to install beyond the core (`httpx`). The structural graph stays local
so traversal/path-highlighting are exact and reproducible.

---

## 9. (Optional) Fully-local AI with Cognee + Ollama

For real hybrid graph+vector recall, fully offline.

### Install

```bash
brew install ollama          # macOS
ollama serve &               # start the local model server
ollama pull llama3.2:3b      # local LLM
ollama pull nomic-embed-text # local embeddings
uv pip install -e ".[cognee]"
```

### Configure -- replace the `memory:` block in `config.yaml`

```yaml
memory:
  backend: "cognee"
  dataset: "repomind"
  persist_path: "graph.json"     # REQUIRED for the cognee backend
  llm_provider: "ollama"
  llm_model: "llama3.2:3b"
  llm_endpoint: "http://localhost:11434/v1"
  embedding_provider: "ollama"
  embedding_model: "nomic-embed-text"
  embedding_endpoint: "http://localhost:11434/api/embed"   # /api/embed, NOT /api/embeddings
  embedding_dimensions: 768
  graph_provider: "kuzu"
  huggingface_tokenizer: "bert-base-uncased"
  access_control: false
```

### Run

```bash
export HF_HUB_OFFLINE=1                              # use cached tokenizer after first run
uv run repomind --config config.yaml backfill       # ingest + cognify (slow on CPU)
uv run repomind --config config.yaml ask "Who owns the auth module and why?"
uv run repomind --config config.yaml serve --port 8000
```

See `docs/LOCAL_COGNEE.md` for the full walkthrough and troubleshooting.

---

## 10. (Optional) Keep the graph always up to date

Three independent ways, all idempotent (no duplicates):

### A. Live webhooks (real-time)

Expose your server (any tunneler you are permitted to use), then add a webhook in
GitHub: **repo -> Settings -> Webhooks -> Add webhook**:

- Payload URL: `https://<your-public-url>/webhook`
- Content type: `application/json`
- Secret: the value of `$REPOMIND_WEBHOOK_SECRET`
- Events: Pushes, Pull requests, Issues

New PRs/issues/pushes ingest within seconds.

### B. Polling (no public URL needed)

```yaml
polling:
  enabled: true
  interval: "15m"
```

### C. Manual refresh (on demand)

```bash
uv run repomind --config config.yaml sync --scope all --full   # re-read + reconcile
uv run repomind --config config.yaml verify                    # confirm graph matches source
```

---

## 11. Quick reference (CLI)

```bash
repomind --config config.yaml backfill            # ingest git + GitHub
repomind --config config.yaml discord export.json # ingest a Discord export
repomind --config config.yaml ask "question"      # query
repomind --config config.yaml sync --scope all --full  # force re-sync
repomind --config config.yaml verify              # consistency check (exit 1 if drift)
repomind --config config.yaml stats               # node/edge counts
repomind --config config.yaml serve --port 8000   # run API + UI
```

---

## 12. Security notes

- Every endpoint requires an API key except `/livez`. Keys are per-client with
  scopes (`read` < `write` < `admin`) and optional per-key rate limiting.
- Fail-closed: with no keys configured, protected endpoints return 503.
- Webhooks are authenticated by GitHub's HMAC signature (set
  `REPOMIND_WEBHOOK_SECRET`, keep `require_signature: true`).
- Keys/tokens/secrets come from the environment only -- never commit them.
  `config.yaml`, `*.sqlite3`, `graph.json`, and `.env` are gitignored.

---

## 13. Troubleshooting

- **503 from the API** -> no API keys active. Make sure the env var named by each
  `api.keys[].token_env` is set, then restart `serve`.
- **401** -> missing/invalid key. **403** -> key lacks the required scope.
- **GitHub 401 (Bad credentials)** -> `GITHUB_TOKEN` is wrong/expired, or
  `repo.github_token_env` points at the wrong var.
- **GitHub rate limits on a huge repo** -> ingest a recent window first; the PAT
  raises the limit.
- **`verify` reports inconsistent** -> usually dangling references (e.g. commits
  citing issues you have not ingested). Run a full `backfill`/`sync` including
  GitHub so issues/PRs exist.
- **Local AI: "Embedding test did not return a valid vector"** -> use
  `/api/embed` (not `/api/embeddings`) for `embedding_endpoint`.
- **Local AI: cognify is very slow** -> expected on CPU; use a smaller model/GPU,
  or use the `memory` backend to validate the flow first.
- More local-AI issues: see `docs/LOCAL_COGNEE.md`.
