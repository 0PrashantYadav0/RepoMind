# RepoMind — Presentation

**Give your repository a brain.** Ask your codebase anything — the answer is the path.

- **Audience:** hackathon judges
- **Length:** 14 slides (~5–6 min + demo)
- **Slide source:** `RepoMind.slides.json` (open in Wibey/Code Puppy and use **Download PPTX**, or paste into the slide-deck skill to re-render).

---

## Slide-by-slide

### 1. Title — RepoMind
Give your repository a brain.
> Hook: turns any git repo into a typed knowledge graph and answers by walking relationships. Explainable by design. Powered by Cognee.

### 2. Your Repo Knows. You Can't Ask It.
"Why was auth built this way, and who decided it?" Buried across commits, closed PRs, stale issues. Keyword search can't connect the dots.

### 3. We Mapped the Entire Cognee Repo  (proof, impact-first)
- Graph Nodes: **18,890**
- Commits: **8,426**
- Pull Requests: **2,802**
- Issues: **771**
> Plus 936 people and 4,815 files — 128,899 typed edges. Ran end to end on the real Cognee OSS repo.

### 4. Not Just Search — Traversal
- **Plain Vector RAG:** returns similar chunks, hopes the answer is inside.
- **RepoMind:** walks typed relationships. The traversal path IS the citation.

### 5. Section — How It Works

### 6. One Idempotent Pipeline, Three Layers
- **Sources:** Git, GitHub, Slack, Discord — one interface.
- **Ingestor:** upsert, resolve refs, park/retry, tombstone.
- **Graph Store:** typed KB + Cognee hybrid graph+vector recall.

### 7. Correctness-First By Design
- **Idempotent** — stable-ID upserts, never dupes.
- **No Silent Loss** — retries + dead-letter queue, replayable.
- **Deterministic Refs** — numeric refs parked, never guessed.
- **Tombstones** — deletes keep history; verify reconciles.

### 8. Pluggable Memory: Pick Your Backend
- **memory** — offline, deterministic, zero AI deps (CI).
- **cognee** — local AI: Ollama + embedded kuzu, offline.
- **cognee_cloud** — hosted AI: just a key + URL, nothing to self-host.

### 9. Section — See It In Action

### 10. What Makes It Shine
- Multi-hop answers: file → commit → PR → reviewer → issue
- Chat↔code bridge: `#123` links messages to PRs/issues
- Live GitHub webhooks — HMAC-verified, fail-closed
- GitHub-themed UI: structured reports + graph zoom & fullscreen
- Secure by default: scoped API keys, per-key rate limits

### 11. Live Demo
Ask → structured cited answer → live traversal graph → zoom / fullscreen the 18,890-node brain.
> **DEMO CUE:** Open the UI, paste the admin key, ask *"who reviewed pull requests about the graph store"*. Show the report card, the seed sources, the numbered traversal, then the fullscreen graph.

### 12. Built to a High Bar
- Tests Passing: **109**
- Lint (ruff): **Clean**
- Memory Backends: **3**
- Secrets Committed: **0**

### 13. What's Next
- Richer query engine: NL planning over the graph
- More connectors: Jira, Linear, Confluence, CI logs
- Incremental live sync at scale (parallel fetch)
- Team dashboards: ownership, review load, decision history

### 14. Thank You / Q&A

---

## Demo runbook (keep off-screen)

1. Server: `uv run repomind --config config.yaml serve --port 8000` (already running).
2. Open `http://127.0.0.1:8000/`, paste the **admin key**, click **Connect**.
3. **Ask tab:** *"who reviewed pull requests about the graph store"* → point at the report + numbered traversal + live graph.
4. **Graph Explorer:** click **Full**, zoom around the graph, toggle tombstoned.
5. Close on the **What's Next** slide.
