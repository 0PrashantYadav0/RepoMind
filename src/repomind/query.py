"""Query engine: turn a natural-language question into an answer grounded in
graph traversal. Entry points come from recall (vector/keyword); the answer is
synthesized from the graph PATHS around the best entry node, and the touched
subgraph is returned for the visualization to highlight.

This deterministic path synthesis is what makes RepoMind explainable: the answer
IS the traversal (e.g. PR -> reviewer -> issue), not an opaque blob.
"""
from __future__ import annotations

from repomind.graph.store import GraphStore
from repomind.models import Edge, EdgeType, Node

# Human-readable phrasing for outgoing/incoming edges from a node's perspective.
_PHRASES = {
    (EdgeType.AUTHORED, "in"): "authored by",
    (EdgeType.AUTHORED, "out"): "authored",
    (EdgeType.REVIEWED, "in"): "reviewed by",
    (EdgeType.REVIEWED, "out"): "reviewed",
    (EdgeType.CLOSES, "out"): "closes",
    (EdgeType.CLOSES, "in"): "closed by",
    (EdgeType.MENTIONS, "out"): "mentions",
    (EdgeType.MENTIONS, "in"): "mentioned by",
    (EdgeType.MODIFIES, "out"): "modifies",
    (EdgeType.MODIFIES, "in"): "modified by",
    (EdgeType.PART_OF, "out"): "part of",
    (EdgeType.DEPENDS_ON, "out"): "depends on",
    (EdgeType.DISCUSSED_IN, "out"): "discussed in",
    (EdgeType.DISCUSSED_IN, "in"): "discusses",
    (EdgeType.DECIDED_IN, "out"): "decided in",
    (EdgeType.COMMENTED_ON, "out"): "commented on",
}


class QueryEngine:
    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def answer(self, question: str, limit: int = 5) -> dict:
        seeds = self.store.search(question, limit=limit)
        if not seeds:
            return {
                "question": question,
                "answer": "I could not find anything relevant in the repository's memory.",
                "seeds": [],
                "facts": [],
                "subgraph": {"nodes": [], "edges": []},
            }

        best = seeds[0]
        facts, sub_nodes, sub_edges = self._explain(best)
        answer_text = self._render(best, facts)
        return {
            "question": question,
            "answer": answer_text,
            "seeds": [self._node_brief(n) for n in seeds],
            "facts": facts,
            "subgraph": {
                "nodes": [self._node_brief(n) for n in sub_nodes],
                "edges": [self._edge_brief(e) for e in sub_edges],
            },
        }

    def _explain(self, node: Node) -> tuple[list[str], list[Node], list[Edge]]:
        facts: list[str] = []
        sub_nodes: dict[str, Node] = {node.id: node}
        sub_edges: list[Edge] = []

        for direction in ("out", "in"):
            for edge, other in self.store.neighbors(node.id, direction=direction):
                phrase = _PHRASES.get((edge.type, direction))
                if phrase is None:
                    continue
                facts.append(f"{phrase} {other.type.value} '{other.title}'")
                sub_nodes[other.id] = other
                sub_edges.append(edge)
                # Second hop: from a PR, walk to the reviewer/issue's own links.
                for edge2, other2 in self.store.neighbors(other.id, direction="out"):
                    if other2.id == node.id:
                        continue
                    phrase2 = _PHRASES.get((edge2.type, "out"))
                    if phrase2 is None:
                        continue
                    sub_nodes[other2.id] = other2
                    sub_edges.append(edge2)
        return facts, list(sub_nodes.values()), sub_edges

    def _render(self, node: Node, facts: list[str]) -> str:
        status = " (DELETED -- shown from history)" if node.status == "deleted" else ""
        head = f"{node.type.value} '{node.title}'{status}"
        if not facts:
            return f"{head}. No further relationships recorded yet."
        return f"{head} -- " + "; ".join(facts) + "."

    @staticmethod
    def _node_brief(n: Node) -> dict:
        return {
            "id": n.id,
            "type": n.type.value,
            "title": n.title,
            "status": n.status,
            "deleted_in": n.deleted_in,
        }

    @staticmethod
    def _edge_brief(e: Edge) -> dict:
        return {"src": e.src, "dst": e.dst, "type": e.type.value}
