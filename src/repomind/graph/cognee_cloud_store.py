"""CogneeCloudStore: the hosted-Cognee adapter -- zero self-hosting.

Unlike CogneeMemoryStore (which runs the Cognee SDK in-process and therefore
needs a local LLM/embeddings/graph deployed), this backend talks to a hosted
Cognee Cloud instance over its REST API. You only supply:

    COGNEE_API_KEY      -- your cloud key (sent as the X-Api-Key header)
    COGNEE_SERVICE_URL  -- your cloud base URL (e.g. https://api.cognee.ai)

There is nothing to install or deploy beyond httpx (a core dependency): no
Ollama, no Kuzu, no torch. Structure stays exact and local (the same
InMemoryGraphStore) so multi-hop traversal and path-highlighting are
reproducible; only the semantic recall (add + cognify + search) is delegated
to the cloud. The HTTP client is injectable so the adapter is fully testable
offline (dependency inversion).
"""
from __future__ import annotations

import io
import logging
from typing import Any, Protocol

from repomind.graph.store import InMemoryGraphStore
from repomind.models import Edge, Node

logger = logging.getLogger(__name__)


class CloudClient(Protocol):
    """Minimal surface of the Cognee Cloud REST API used by this adapter."""

    def add(self, text: str, dataset: str) -> Any: ...
    def cognify(self, dataset: str) -> Any: ...
    def search(self, query: str, search_type: str, dataset: str, top_k: int) -> list: ...
    def memify(self, dataset: str) -> Any: ...


class HttpCloudClient:
    """Real Cognee Cloud client over httpx. Auth via the X-Api-Key header."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 120.0) -> None:
        import httpx  # core dependency

        self._base = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout, headers={"X-Api-Key": api_key})

    def _url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"

    def add(self, text: str, dataset: str) -> Any:
        files = [("data", ("repomind.txt", io.BytesIO(text.encode()), "text/plain"))]
        r = self._http.post(self._url("/api/v1/add"), files=files, data={"datasetName": dataset})
        r.raise_for_status()
        return r.json()

    def cognify(self, dataset: str) -> Any:
        r = self._http.post(self._url("/api/v1/cognify"), json={"datasets": [dataset]})
        r.raise_for_status()
        return r.json()

    def search(self, query: str, search_type: str, dataset: str, top_k: int) -> list:
        payload = {
            "query": query,
            "search_type": search_type,
            "datasets": [dataset],
            "top_k": top_k,
        }
        r = self._http.post(self._url("/api/v1/search"), json=payload)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]

    def memify(self, dataset: str) -> Any:
        r = self._http.post(self._url("/api/v1/memify"), json={"dataset_name": dataset})
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._http.close()


class CogneeCloudStore:
    """Hybrid adapter: exact local structure + hosted-Cognee semantic recall."""

    def __init__(
        self,
        memory_config,
        api_key: str | None,
        service_url: str | None,
        client: CloudClient | None = None,
    ) -> None:
        self.cfg = memory_config
        self.dataset = memory_config.dataset
        self._graph = InMemoryGraphStore()
        if getattr(memory_config, "persist_path", ""):
            self._graph.load(memory_config.persist_path)
        self._pending_texts: list[str] = []
        if client is not None:
            self._client: CloudClient = client
        else:
            if not api_key or not service_url:
                raise ValueError(
                    "cognee_cloud backend needs COGNEE_API_KEY and a service URL "
                    "(memory.service_url or COGNEE_SERVICE_URL)."
                )
            self._client = HttpCloudClient(service_url, api_key)

    def save(self, path: str) -> None:
        self._graph.save(path)

    # -- structure (delegate to the exact local graph) ----------------------
    def upsert_node(self, node: Node) -> None:
        self._graph.upsert_node(node)
        if node.status == "active":
            self._pending_texts.append(node.text_for_embedding())

    def upsert_edge(self, edge: Edge) -> None:
        self._graph.upsert_edge(edge)

    def get_node(self, node_id: str) -> Node | None:
        return self._graph.get_node(node_id)

    def has_node(self, node_id: str) -> bool:
        return self._graph.has_node(node_id)

    def tombstone_node(self, node_id: str, deleted_in: str | None = None) -> bool:
        return self._graph.tombstone_node(node_id, deleted_in)

    def hard_delete(self, node_id: str) -> bool:
        return self._graph.hard_delete(node_id)

    def neighbors(self, node_id, edge_types=None, direction="out"):
        return self._graph.neighbors(node_id, edge_types, direction)

    def all_nodes(self, include_deleted: bool = True) -> list[Node]:
        return self._graph.all_nodes(include_deleted)

    def all_edges(self) -> list[Edge]:
        return self._graph.all_edges()

    def counts(self) -> dict:
        return self._graph.counts()

    # -- Cognee Cloud memory lifecycle --------------------------------------
    def remember_flush(self) -> None:
        """Push buffered node texts to the cloud (one blob) and cognify."""
        if not self._pending_texts:
            return
        combined = "\n\n".join(self._pending_texts)
        self._pending_texts.clear()
        try:
            self._client.add(combined, self.dataset)
            self._client.cognify(self.dataset)
        except Exception as exc:  # noqa: BLE001
            # Recall degrades to local keyword search; structure is intact.
            logger.warning("cognee_cloud remember/cognify failed: %r", exc)

    def improve(self) -> None:
        memify = getattr(self._client, "memify", None)
        if not callable(memify):
            return
        try:
            memify(self.dataset)
        except Exception as exc:  # noqa: BLE001
            logger.debug("cognee_cloud memify best-effort failure: %r", exc)

    def forget(self, target: str | None = None) -> None:
        # Structural erasure already happened locally; cloud pruning is
        # best-effort and intentionally not assumed to exist on every plan.
        logger.debug("cognee_cloud forget is local-only for target %r", target)

    def search(self, query: str, limit: int = 10, include_deleted: bool = False) -> list[Node]:
        """Hybrid recall via the cloud; map hits back to typed graph nodes.

        Falls back to the deterministic local search if the cloud returns
        nothing recognizable, so the system degrades gracefully.
        """
        try:
            raw = self._client.search(
                query, self.cfg.cloud_search_type, self.dataset, top_k=max(limit, 15)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("cognee_cloud search failed, using local: %r", exc)
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
        return self._graph.search(query, limit=limit, include_deleted=include_deleted)
