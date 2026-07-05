# RepoMind — Demo Video Script

**Runtime target:** ~3–4 minutes
**Demo subject:** the real [Cognee](https://github.com/topoteretes/cognee) open-source repo — its code, **all its PRs**, issues, and reviewers.
**AI backend:** Cognee hybrid graph + vector memory, powered by the best model (**OpenAI GPT-4o** for entity extraction + `text-embedding-3-large`).

> Fitting twist: RepoMind uses **Cognee** as its memory layer, and in this demo it gives **the Cognee repo itself** a brain. Cognee, meet Cognee. 

---

## 0. Before you hit record (prep — not filmed)

1. Put your secrets in `.env` (already scaffolded, gitignored):
   ```
   GITHUB_TOKEN=ghp_...            # PAT, public_repo scope
   OPENAI_API_KEY=sk-...           # powers GPT-4o cognify + embeddings
   LLM_API_KEY=sk-...              # same OpenAI key
   EMBEDDING_API_KEY=sk-...        # same OpenAI key
   ```
2. Do a **dry run first** so cognify is warm and nothing surprises you on camera:
   ```bash
   LITE=1 ./scripts/demo_cognee.sh
   ```
   - `LITE=1` = shallow clone (last 50 commits) → fast, cheap, recordable.
   - Drop `LITE=1` for the full "all PRs + full history" ingest (slower, costs more).
3. Note the **admin key** it prints — you'll paste it in the UI.
4. Have two terminal tabs ready: one for the server, one for CLI `ask` commands.
5. Pre-open `http://127.0.0.1:8000/` but stay on the connect screen.

---

## 1. Hook — the problem (0:00–0:20)

**On screen:** your face cam / a slide with a tangled repo graphic, or just the Cognee repo's GitHub page scrolling through hundreds of PRs.

**Narration:**
> "Every repo hides its real story in git blame, closed PRs, and stale issues.
> Ask *'why is the auth layer built this way, and who decided it?'* and you're
> archaeology-ing through a thousand commits. Plain vector search just returns
> similar-looking text and hopes the answer's inside. **RepoMind** does something
> different — it turns a repository into a *typed knowledge graph* and answers by
> **walking the relationships**."

---

## 2. What RepoMind is (0:20–0:40)

**On screen:** the architecture diagram from the README (Sources → Ingestor → GraphStore → Query), or a simple animation of `file → commit → PR → reviewer → issue`.

**Narration:**
> "It ingests commits, files, pull requests, issues, people, and chat into one> graph — then answers questions with **multi-hop traversal**. The answer *is*
> the path, so it's explainable. Today I'm pointing it at the real **Cognee**
> open-source repo — every commit, every PR, every reviewer — using **GPT-4o**
> as the brain."

---

## 3. Ingest the Cognee repo (0:40–1:20)

**On screen:** Terminal. Run the demo script.

**Type:**
```bash
./scripts/demo_cognee.sh
```

**Narration (while it runs):**
> "One command. It clones the Cognee repo, then RepoMind reads the git history
> and pulls **all the pull requests and issues** straight from the GitHub API —
> authors, reviewers, the `Fixes #123` links, everything. Each node's text gets
> pushed into Cognee and **cognified** with GPT-4o to build the hybrid
> graph+vector memory."

**On screen:** Let the `stats` output land and point your cursor at it:
```json
{ "nodes": ..., "edges": ..., "by_type": { "Commit": ..., "PullRequest": ..., "Issue": ..., "Person": ..., "File": ..., "Module": ... } }
```

**Narration:**
> "There's the graph — thousands of nodes, all typed, all connected."

---

## 4. Ask multi-hop questions (1:20–2:20)  the money shot

**On screen:** Browser at `http://127.0.0.1:8000/`. Paste the **admin key**, click **Connect**. Go to the **Ask** tab.

**Narration:**
> "Now the fun part. I'll ask questions that need *traversal*, not just search."

**Ask these (type each, let the answer + traversal + live graph render):**

1. `Who are the top reviewers on this repo and what did they review?`
2. `Which PRs mention the graph store and who authored them?`
3. `What issues were closed by pull requests, and who fixed them?`
4. `Which files change most often and in which PRs?`

**Narration (point at the traversal panel + the force-graph lighting up):**
> "Look at this — it doesn't just give an answer, it shows the **path** it
> walked: file → commit → pull request → reviewer → issue. That traversal *is*
> the citation. And because Cognee's doing hybrid graph+vector recall with
> GPT-4o, it understands the question, not just keywords."

**Optional CLI beat (second terminal), to show it's not UI-only:**
```bash
uv run repomind --config config.cognee.yaml ask "Why was the vector store abstraction introduced and who reviewed it?"
```

---

## 5. Graph Explorer (2:20–2:45)

**On screen:** Click the **Graph Explorer** tab. Slowly pan/zoom the force graph. Toggle **show tombstoned**.

**Narration:**
> "Here's the whole brain — colored by node type. Commits, PRs, issues, people,
> files. Deleted things aren't erased; they're **tombstoned**, so RepoMind can
> still tell you what a file *used* to do and which PR removed it. History is
> preserved on purpose."

---

## 6. Live updates + the chat↔code bridge (2:45–3:10)

**On screen:** The **Ingest** tab. Post a chat message that references an issue/PR number, e.g.:
> `"Reviewed the retry logic in #<real_PR_number>, looks solid — merging."`

Then jump back to **Ask** and query it.

**Narration:**
> "It's not a one-time snapshot. New PRs, pushes, and even chat messages flow in
> live — via webhook, poller, or this low-code ingest. A message that mentions
> `#123` automatically links to that PR — the **chat-to-code bridge**. Every path
> is **idempotent**: re-ingesting never creates duplicates."

---

## 7. Correctness + the model (3:10–3:35)

**On screen:** Terminal — run verify.

**Type:**
```bash
uv run repomind --config config.cognee.yaml verify
```

**Narration:**
> "Correctness-first: `verify` re-reads the source of truth and reconciles the
> graph — nothing silently lost, references never guessed. And the whole thing is
> **backend-swappable**: GPT-4o today, Claude, or a fully-local Ollama model with
> zero cloud — same graph, same answers."

---

## 8. Close (3:35–4:00)

**On screen:** Back to the graph, slow zoom out. Title card: **RepoMind — give your repo a brain.**

**Narration:**
> "RepoMind: a typed knowledge graph over your repo, explainable multi-hop
> answers, correctness-first ingestion, and pluggable AI memory powered by
> Cognee. I pointed it at Cognee's own repo — now it knows Cognee better than
> most of its contributors. Thanks for watching."

---

## Cheat sheet (keep off-screen)

| Beat | Command |
|---|---|
| One-shot demo | `./scripts/demo_cognee.sh` (or `LITE=1 …` for a fast take) |
| Stats | `uv run repomind --config config.cognee.yaml stats` |
| Ask (CLI) | `uv run repomind --config config.cognee.yaml ask "…"` |
| Verify | `uv run repomind --config config.cognee.yaml verify` |
| UI | `http://127.0.0.1:8000/` → paste admin key → Connect |

**Recording tips**
- Record at 1080p+; bump terminal font size to ~18pt.
- If the full ingest is slow, ingest **before** recording, then just run `serve`
  during the take and let the graph already be populated.
- Pre-test every question so you know the answers look good on camera.
- Keep the traversal panel visible — that "here's the path" moment is the pitch.
