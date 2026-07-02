"""Standalone smoke test: local Cognee + local Ollama (no cloud, no API key)."""
import asyncio
import os

# Point Cognee's LLM + embeddings at the local Ollama server.
os.environ.setdefault("CACHING", "false")

import cognee


def configure():
    c = cognee.config
    # LLM via Ollama (OpenAI-compatible endpoint).
    c.set_llm_provider("ollama")
    c.set_llm_model("llama3.2:3b")
    c.set_llm_endpoint("http://localhost:11434/v1")
    c.set_llm_api_key("ollama")  # dummy; Ollama ignores it
    # Embeddings via Ollama.
    c.set_embedding_provider("ollama")
    c.set_embedding_model("nomic-embed-text")
    c.set_embedding_endpoint("http://localhost:11434/api/embed")
    c.set_embedding_dimensions(768)
    # Graph store: Kuzu (embedded, fully local, no server).
    c.set_graph_database_provider("kuzu")
    # Vector store defaults to LanceDB (local). Fully self-hosted.


async def main():
    configure()
    await cognee.prune.prune_data()
    await cognee.prune.prune_system(metadata=True)

    print(">> remember()")
    await cognee.add(
        "Ada Lovelace authored the commit 'Fix login bug' which modifies auth.py "
        "and closes issue #12 about the login returning None.",
        dataset_name="repomind",
    )
    print(">> cognify() (build the graph)")
    await cognee.cognify(datasets=["repomind"])

    print(">> search()")
    results = await cognee.search(query_text="Who fixed the login bug?")
    print("RESULTS:")
    for r in results:
        print("  -", str(r)[:300])


if __name__ == "__main__":
    asyncio.run(main())
