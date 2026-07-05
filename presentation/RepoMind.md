# RepoMind — YouTube Demo Video Script (max 3:00)

Target: **under 3 minutes**. ~430 words (~150 wpm). Record at 1080p, big fonts.
Have the server running and the Cognee graph already ingested so the demo is instant.

> Covers: About the project · Tech stack & architecture · Demo · Learning & growth.
> Slides: open `RepoMind-deck.html` fullscreen (press F) and advance with arrow keys.

---

## 0:00 - 0:10 · Cold open (title slide)
> "This is RepoMind — it gives your repository a brain. Ask your codebase
> anything in plain English, and the answer comes with the exact path that
> proves it."

## 0:10 - 0:50 · About the project (~40s)
> "Every repo hides its real story in commits, closed PRs and stale issues.
> Ask why the auth layer was built this way and who decided it — and normal
> search just returns similar-looking text and hopes.
>
> RepoMind is different. It turns commits, pull requests, issues, people and
> chat into one typed knowledge graph, then answers by walking the relationships
> — multi-hop, and fully explainable.
>
> To prove it, we pointed it at the entire Cognee open-source repo: over
> eighteen thousand nodes — eight thousand commits, twenty-eight hundred pull
> requests, and every issue — all connected."

## 0:50 - 1:30 · Tech stack & architecture (~40s)
> "The stack is deliberately lean: Python and FastAPI for the API and webhook
> server, GitPython and PyGithub for sources, a vanilla-JS force-graph UI, and
> Cognee for hybrid graph-plus-vector memory.
>
> The architecture is three layers behind one idempotent pipeline. Sources all
> speak one interface. Everything funnels through a single ingestor that upserts
> by stable ID, resolves references, and tombstones deletions — so re-running
> never duplicates and never silently loses data. Recall is pluggable:
> in-memory, local AI, or hosted Cognee Cloud — one config line."

## 1:30 - 2:35 · Demo (~65s)
> "Here it is live. I paste my API key and connect.
>
> On the Ask tab I'll ask: who reviewed pull requests about the graph store?"

*(type it, submit)*

> "Instantly I get a structured report — the answer, the sources it's grounded
> on, and a numbered traversal showing every hop it took: file, to commit, to
> pull request, to reviewer. That traversal IS the citation.
>
> And it's interactive — here's the live graph of that path. I can zoom, fit,
> and go fullscreen to explore the whole eighteen-thousand-node brain."

*(click fullscreen, zoom around briefly)*

> "Every answer is explainable, and every endpoint is secured with scoped API keys."

## 2:35 - 3:00 · Learning & growth (~25s)
> "Building this taught us that graph traversal beats plain vector search when
> you need answers you can trust — and that scaling to a real six-thousand-commit
> repo is all about idempotent, bounded ingestion. RepoMind: give your
> repository a brain. Thanks for watching."

---

## Recording checklist
- Server: `uv run repomind --config config.yaml serve --port 8000`
- Cognee graph already ingested (instant demo).
- Slides: `RepoMind-deck.html` (fullscreen, arrow keys).
- Pre-type the demo question; confirm the answer looks good first.
- Keep the traversal panel + fullscreen graph on screen — that's the money shot.
- Talk budget: ~2:55. Leave a few seconds of headroom.
