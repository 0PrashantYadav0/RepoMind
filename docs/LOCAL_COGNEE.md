# Running RepoMind on local Cognee + Ollama (fully self-hosted)

This is a verified, 100% local setup: no Cognee Cloud, no API keys, no external
LLM. Ollama serves the LLM and embeddings; Cognee stores the hybrid graph+vector
memory in an embedded kuzu graph + LanceDB, all on disk.

Verified end to end through RepoMind's own CLI: backfill -> cognify -> ask
returned the correct, traversed answer.

## 1. Install

```bash
# Ollama (macOS)
brew install ollama
ollama serve &                       # start the local model server

# Local models: an LLM + an embedding model
ollama pull llama3.2:3b
ollama pull nomic-embed-text

# RepoMind with the Cognee extra + the HF tokenizer dependency
uv pip install -e ".[cognee]"
uv pip install transformers          # needed for the embedding tokenizer
```

## 2. Configure (`config.yaml`)

```yaml
memory:
  backend: "cognee"
  dataset: "repomind"
  persist_path: "graph.json"     # REQUIRED: structural graph must survive between runs
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

RepoMind applies these via Cognee's config setters and sets the required env
switches (`ENABLE_BACKEND_ACCESS_CONTROL`, `HUGGINGFACE_TOKENIZER`) for you.

## 3. Run

```bash
export HF_HUB_OFFLINE=1                       # use the cached tokenizer, no HF calls
uv run repomind --config config.yaml backfill   # ingest + cognify (slow on CPU)
uv run repomind --config config.yaml ask "Who fixed the login bug and who wrote it?"
```

Expected: an answer naming the author, with a traversal of the commits/files
they touched.

## Gotchas discovered (and how they're handled)

1. **Embedding endpoint schema.** Cognee's Ollama embedder POSTs
   `{"model","input","dimensions"}` -> use `/api/embed` (newer schema), not the
   older `/api/embeddings` (which wants `"prompt"`). Wrong endpoint =
   "Embedding test did not return a valid vector".
2. **Embedding tokenizer needs `transformers`** and downloads a small HF
   tokenizer once. Set `huggingface_tokenizer` (e.g. `bert-base-uncased`); it is
   only used for token-counting during chunking, so any standard tokenizer
   works. After the first download, run with `HF_HUB_OFFLINE=1`.
3. **Graph provider.** Cognee 1.2's default (`ladybug`) and `kuzu` may try to
   download a JSON extension from `extension.ladybugdb.com` on first use. Ensure
   that host is reachable (it is over the open internet). `networkx` is no longer
   supported in 1.2.
4. **Access control.** Cognee 1.2 enables multi-tenant access control by default,
   which the embedded graph can't satisfy -> set `access_control: false`
   (RepoMind exports `ENABLE_BACKEND_ACCESS_CONTROL=false`).
5. **Per-process structural graph.** RepoMind keeps the typed graph (for exact
   traversal) alongside Cognee's recall. It is persisted to `persist_path`, so
   `persist_path` is **required** for the Cognee backend or `ask`/`serve` will
   start with an empty structural graph (Cognee's own store persists separately
   on disk under its system directory).
6. **Don't `cognee.add()` tiny strings.** Short, path-like strings (e.g.
   "File: db.py") get treated as filenames. RepoMind sends one combined text
   document per flush to avoid this.
7. **CPU speed.** `cognify` runs the local LLM to extract entities; on CPU this
   takes minutes for even a small repo. A GPU or a smaller model speeds it up.

## Smoke test

`scripts/cognee_ollama_smoke.py` exercises Cognee + Ollama directly (remember ->
cognify -> search) without RepoMind, useful for isolating environment issues.
