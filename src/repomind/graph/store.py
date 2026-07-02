"""GraphStore: the abstraction over the knowledge graph + semantic recall.

`InMemoryGraphStore` is the default, dependency-free implementation used in
tests and for local runs. `CogneeMemoryStore` (cognee_store.py) is the real
adapter that pushes the same graph into Cognee Cloud for hybrid recall.

Keeping Cognee behind this interface means the entire pipeline is testable
with zero network/keys (dependency inversion).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from repomind.models import Edge, EdgeType, Node, NodeType


@runtime_checkable
class GraphStore(Protocol):
    def upsert_node(self, node: Node) -> None: ...
    def upsert_edge(self, edge: Edge) -> None: ...
    def get_node(self, node_id: str) -> Node | None: ...
    def has_node(self, node_id: str) -> bool: ...
    def tombstone_node(self, node_id: str, deleted_in: str | None = None) -> bool: ...
    def hard_delete(self, node_id: str) -> bool: ...
    def neighbors(
        self, node_id: str, edge_types: list[EdgeType] | None = None, direction: str = "out"
    ) -> list[tuple[Edge, Node]]: ...
    def search(self, query: str, limit: int = 10, include_deleted: bool = False) -> list[Node]: ...
    def all_nodes(self, include_deleted: bool = True) -> list[Node]: ...
    def all_edges(self) -> list[Edge]: ...
    def counts(self) -> dict: ...


class InMemoryGraphStore:
    """A correct, idempotent, in-process knowledge graph.

    - upserts are keyed by stable ID (idempotent: same ID merges, never dupes)
    - deletions are tombstones by default (history-preserving); hard_delete erases
    - search is a simple, deterministic keyword scorer (good enough offline;
      the Cognee adapter replaces this with hybrid vector + graph recall)
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple[str, str, str], Edge] = {}

    # -- nodes ---------------------------------------------------------------
    def upsert_node(self, node: Node) -> None:
        existing = self._nodes.get(node.id)
        if existing is None:
            self._nodes[node.id] = node
            return
        # Merge: new non-empty fields win; attributes are merged; never resurrect
        # a hard-deleted node implicitly (it would not be present anyway).
        merged_attrs = {**existing.attributes, **node.attributes}
        existing.title = node.title or existing.title
        existing.body = node.body or existing.body
        existing.attributes = merged_attrs
        existing.schema_version = max(existing.schema_version, node.schema_version)
        # An upsert from a live source reactivates a previously tombstoned node
        # only if the incoming node is explicitly active.
        if node.status == "active":
            existing.status = "active"
            existing.deleted_in = None

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def tombstone_node(self, node_id: str, deleted_in: str | None = None) -> bool:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        node.status = "deleted"
        node.deleted_in = deleted_in
        return True

    def hard_delete(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        # Remove dangling edges touching this node.
        for key in [k for k in self._edges if k[0] == node_id or k[1] == node_id]:
            del self._edges[key]
        return True

    # -- edges ---------------------------------------------------------------
    def upsert_edge(self, edge: Edge) -> None:
        existing = self._edges.get(edge.key)
        if existing is None:
            self._edges[edge.key] = edge
        else:
            existing.attributes = {**existing.attributes, **edge.attributes}

    def neighbors(
        self, node_id: str, edge_types: list[EdgeType] | None = None, direction: str = "out"
    ) -> list[tuple[Edge, Node]]:
        wanted = {e.value for e in edge_types} if edge_types else None
        out: list[tuple[Edge, Node]] = []
        for edge in self._edges.values():
            if wanted is not None and edge.type.value not in wanted:
                continue
            if direction == "out" and edge.src == node_id:
                other = self._nodes.get(edge.dst)
            elif direction == "in" and edge.dst == node_id:
                other = self._nodes.get(edge.src)
            elif direction == "both" and (edge.src == node_id or edge.dst == node_id):
                other_id = edge.dst if edge.src == node_id else edge.src
                other = self._nodes.get(other_id)
            else:
                continue
            if other is not None:
                out.append((edge, other))
        return out

    # -- query ---------------------------------------------------------------
    def search(self, query: str, limit: int = 10, include_deleted: bool = False) -> list[Node]:
        terms = [t for t in _tokenize(query) if t]
        scored: list[tuple[float, Node]] = []
        for node in self._nodes.values():
            if not include_deleted and node.status == "deleted":
                continue
            hay = _tokenize(node.text_for_embedding())
            if not hay:
                continue
            score = sum(hay.count(t) for t in terms)
            # Light boost for title matches.
            title_tokens = _tokenize(node.title)
            score += sum(2 for t in terms if t in title_tokens)
            if score > 0:
                scored.append((score, node))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        return [n for _, n in scored[:limit]]

    def all_nodes(self, include_deleted: bool = True) -> list[Node]:
        return [n for n in self._nodes.values() if include_deleted or n.status != "deleted"]

    def all_edges(self) -> list[Edge]:
        return list(self._edges.values())

    def counts(self) -> dict:
        by_type: dict[str, int] = {}
        for n in self._nodes.values():
            by_type[n.type.value] = by_type.get(n.type.value, 0) + 1
        tombstoned = sum(1 for n in self._nodes.values() if n.status == "deleted")
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "tombstoned": tombstoned,
            "by_type": by_type,
        }

    # -- persistence (optional) ---------------------------------------------
    def save(self, path: str | Path) -> None:
        payload = {
            "nodes": [n.model_dump(mode="json") for n in self._nodes.values()],
            "edges": [e.model_dump(mode="json") for e in self._edges.values()],
        }
        Path(path).write_text(json.dumps(payload, indent=2, default=str))

    def load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            return
        payload = json.loads(p.read_text())
        for nd in payload.get("nodes", []):
            node = Node(**{**nd, "type": NodeType(nd["type"])})
            self._nodes[node.id] = node
        for ed in payload.get("edges", []):
            edge = Edge(**{**ed, "type": EdgeType(ed["type"])})
            self._edges[edge.key] = edge


def _tokenize(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(t) > 1]
