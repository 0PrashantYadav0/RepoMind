# RepoMind — Presentation

**Give your repository a brain.** Ask your codebase anything — the answer is the path.

- **Purpose:** submission deck + YouTube demo (max 3 min)
- **Covers the rubric:** About the project · Tech stack & architecture · Demo · Learning & growth
- **Deliverables in this folder:**
  - `RepoMind-deck.html` — self-contained slide deck (open in any browser; arrow keys + `F` for fullscreen). Use this to present/record.
  - `RepoMind.slides.json` — slide source for the slide-deck tool (Download PPTX).
  - `RepoMind-video-script.md` — timed narration, under 3:00.
  - `RepoMind.md` — this outline + demo runbook.

---

## Deck outline (14 slides in the HTML deck)

1. **Title** — RepoMind: give your repository a brain
2. *Section — About the Project*
3. **Your Repo Knows. You Can't Ask It.** — what it is + the problem
4. **Real repo. Real scale.** — 18,890 nodes / 8,426 commits / 2,802 PRs / 771 issues
5. *Section — Tech Stack & Architecture*
6. **The Stack** — Python, FastAPI, Pydantic, GitPython/PyGithub, Cognee, force-graph UI, pytest/ruff/uv
7. **One Idempotent Pipeline, Three Layers** — Sources -> Ingestor -> Graph Store
8. **Correctness-First By Design** — idempotent, no silent loss, deterministic refs, tombstones
9. **Pick Your Backend** — memory / cognee / cognee_cloud
10. *Section — Demo*
11. **Ask -> Answer -> Traversal Graph** — demo steps
12. *Section — Learning & Growth*
13. **What We Learned** — traversal > vector RAG, idempotency, scaling, pluggable memory
14. **Thank You**

---

## Demo runbook (keep off-screen)

1. Server: `uv run repomind --config config.yaml serve --port 8000` (already running).
2. Open `http://127.0.0.1:8000/`, paste the **admin key**, click **Connect**.
3. **Ask tab:** *"who reviewed pull requests about the graph store"* -> point at the report + numbered traversal + live graph.
4. **Graph:** click **Full**, zoom around, then wrap.
5. Close on the **Learning & Growth** slide.

---

## Recording the video (under 3:00)

Read from `RepoMind-video-script.md`. Screen-record `RepoMind-deck.html` (fullscreen)
for the slide portions, and the running RepoMind UI for the demo portion.
