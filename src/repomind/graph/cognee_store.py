"""CogneeMemoryStore: the real, production adapter (Cognee Cloud).

Design: we keep a deterministic typed graph (the same InMemoryGraphStore logic,
optionally persisted) as the system of record for STRUCTURE so that multi-hop
traversal and path-highlighting are exact and reproducible. In parallel, every
node's text is pushed into Cognee via remember()/cognify so that recall() gets
hybrid vector + graph semantics, and improve()/forget() drive the memory
lifecycle.

This module lazy-imports `cognee`, so importing repomind never requires it.
The exact SDK call names can vary slightly across Cognee versions; the wrappers
below are isolated in one place so they are trivial to adjust.

Enable via config: memory.backend = "cognee" and COGNEE_API_KEY in the env.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from repomind.graph.store import InMemoryGraphStore
from repomind.models import Edge, Node

logger = logging.getLogger(__name__)


def _run(coro: Any) -> Any:
    """Run an async Cognee call from sync code and always return a real result.

    If no loop is running, use asyncio.run directly. If a loop IS already running
    (e.g. called from within an async context), run the coroutine to completion on
    a dedicated thread so we never return an un-awaited Future (BUG-1).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None or not loop.is_running():
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def _worker() -> None:
        result["value"] = asyncio.run(coro)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    return result.get("value")


class CogneeMemoryStore:
    """Hybrid adapter. Structure is exact (local graph); recall is Cognee.

    Works with Cognee Cloud (just an API key) OR a fully local, self-hosted
    Cognee (local LLM + embeddings via Ollama, embedded kuzu graph). The local
    knobs come from MemoryConfig; only non-empty fields are applied.
    """

    def __init__(self, memory_config, api_key: str | None) -> None:
        self.cfg = memory_config
        self.dataset = memory_config.dataset
        self._graph = InMemoryGraphStore()
        # The structural graph is the source of truth for traversal; persist it
        # across processes (Cognee persists its own vector/graph store on disk).
        if getattr(memory_config, "persist_path", ""):
            self._graph.load(memory_config.persist_path)
        self._pending_texts: list[tuple[str, str]] = []  # (node_id, text)
        self._cognee = self._init_cognee(api_key)

    def save(self, path: str) -> None:
        """Persist the structural graph so a later process can traverse it."""
        self._graph.save(path)

    def _init_cognee(self, api_key: str | None):
        import os

        cfg = self.cfg
        # Some Cognee switches are read from the environment at import/config
        # time, so set them before configuring.
        if not cfg.access_control:
            os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")
        if cfg.huggingface_tokenizer:
            os.environ.setdefault("HUGGINGFACE_TOKENIZER", cfg.huggingface_tokenizer)

        import cognee  # lazy: only needed for the real backend

        c = cognee.config
        if api_key:
            try:
                c.set_llm_api_key(api_key)
            except Exception:  # noqa: BLE001
                os.environ.setdefault("COGNEE_API_KEY", api_key)
        # Apply local/self-hosted tuning (only non-empty fields).
        if cfg.llm_provider:
            c.set_llm_provider(cfg.llm_provider)
        if cfg.llm_model:
            c.set_llm_model(cfg.llm_model)
        if cfg.llm_endpoint:
            c.set_llm_endpoint(cfg.llm_endpoint)
            if not api_key:
                c.set_llm_api_key("ollama")  # dummy; local Ollama ignores it
        if cfg.embedding_provider:
            c.set_embedding_provider(cfg.embedding_provider)
        if cfg.embedding_model:
            c.set_embedding_model(cfg.embedding_model)
        if cfg.embedding_endpoint:
            c.set_embedding_endpoint(cfg.embedding_endpoint)
        if cfg.embedding_dimensions:
            c.set_embedding_dimensions(cfg.embedding_dimensions)
        if cfg.graph_provider:
            c.set_graph_database_provider(cfg.graph_provider)
        return cognee

    # -- structure (delegate to the exact local graph) ----------------------
    def upsert_node(self, node: Node) -> None:
        self._graph.upsert_node(node)
        if node.status == "active":
            self._pending_texts.append((node.id, node.text_for_embedding()))

    def upsert_edge(self, edge: Edge) -> None:
        self._graph.upsert_edge(edge)

    def get_node(self, node_id: str) -> Node | None:
        return self._graph.get_node(node_id)

    def has_node(self, node_id: str) -> bool:
        return self._graph.has_node(node_id)

    def tombstone_node(self, node_id: str, deleted_in: str | None = None) -> bool:
        return self._graph.tombstone_node(node_id, deleted_in)

    def hard_delete(self, node_id: str) -> bool:
        ok = self._graph.hard_delete(node_id)
        if ok:
            self.forget(node_id)  # surgically erase from Cognee too
        return ok

    def neighbors(self, node_id, edge_types=None, direction="out"):
        return self._graph.neighbors(node_id, edge_types, direction)

    def all_nodes(self, include_deleted: bool = True) -> list[Node]:
        return self._graph.all_nodes(include_deleted)

    def all_edges(self) -> list[Edge]:
        return self._graph.all_edges()

    def counts(self) -> dict:
        return self._graph.counts()

    # -- Cognee memory lifecycle --------------------------------------------
    def remember_flush(self) -> None:
        """Push buffered node texts into Cognee and build the graph (cognify).

        We join all buffered node texts into a single text document. Calling
        cognee.add() per tiny string is fragile -- Cognee's ingestion treats
        short path-like strings (e.g. 'File: db.py') as filenames to read from
        disk. One combined text blob is unambiguously content.
        """
        if not self._pending_texts:
            return
        texts = [t for _, t in self._pending_texts]
        self._pending_texts.clear()
        combined = "\n\n".join(texts)

        async def _do():
            await self._cognee.add(combined, dataset_name=self.dataset)
            await self._cognee.cognify(datasets=[self.dataset])

        _run(_do())

    def improve(self) -> None:
        """Run post-ingestion enrichment / memify on the dataset."""
        fn = getattr(self._cognee, "memify", None) or getattr(self._cognee, "improve", None)
        if fn is None:
            return

        async def _do():
            try:
                await fn(datasets=[self.dataset])
            except TypeError:
                await fn()

        _run(_do())

    def forget(self, target: str | None = None) -> None:
        """Surgically delete from Cognee. Without a target, prune the dataset."""
        async def _do():
            try:
                if target is not None and hasattr(self._cognee, "delete"):
                    await self._cognee.delete(target, dataset_name=self.dataset)
                elif hasattr(self._cognee, "prune"):
                    await self._cognee.prune.prune_data(dataset_name=self.dataset)
            except Exception as exc:
                # Forget is best-effort; structure removal already happened
                # locally, so memory stays consistent. Log so it is observable.
                logger.debug("cognee forget best-effort failure: %r", exc)

        _run(_do())

    def search(self, query: str, limit: int = 10, include_deleted: bool = False) -> list[Node]:
        """Hybrid recall via Cognee; map hits back to typed graph nodes.

        Falls back to the deterministic local search if Cognee returns nothing
        recognizable, so the system degrades gracefully.
        """
        async def _do():
            search_fn = getattr(self._cognee, "search", None)
            if search_fn is None:
                return []
            try:
                return await search_fn(query_text=query)
            except TypeError:
                return await search_fn(query)

        try:
            raw = _run(_do())
        except Exception:
            raw = []

        hits: list[Node] = []
        seen: set[str] = set()
        for item in raw or []:
            text = item if isinstance(item, str) else str(item)
            for node in self._graph.all_nodes(include_deleted=include_deleted):
                if node.id in seen:
                    continue
                if node.title and node.title.lower() in text.lower():
                    hits.append(node)
                    seen.add(node.id)
        if hits:
            return hits[:limit]
        # Graceful fallback to exact local keyword search.
        return self._graph.search(query, limit=limit, include_deleted=include_deleted)
