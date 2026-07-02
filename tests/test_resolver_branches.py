"""Cover the remaining resolver branches: PR_NUMBER (present/absent) and the
unhandled-kind fallback."""
from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import EdgeType, Node, NodeType, RefKind, Reference
from repomind.pipeline.resolver import resolve_reference


def test_pr_number_parked_when_absent():
    s = InMemoryGraphStore()
    s.upsert_node(Node(id=ids.issue_id("demo/repo", 1), type=NodeType.ISSUE, title="x"))
    ref = Reference(kind=RefKind.PR_NUMBER, value="42", edge=EdgeType.MENTIONS)
    res = resolve_reference(ids.issue_id("demo/repo", 1), ref, "demo/repo", s)
    assert res.edge is None and res.unresolved is not None


def test_pr_number_resolves_when_present():
    s = InMemoryGraphStore()
    s.upsert_node(Node(id=ids.issue_id("demo/repo", 1), type=NodeType.ISSUE, title="x"))
    s.upsert_node(Node(id=ids.pr_id("demo/repo", 42), type=NodeType.PULL_REQUEST, title="pr"))
    ref = Reference(kind=RefKind.PR_NUMBER, value="42", edge=EdgeType.MENTIONS)
    res = resolve_reference(ids.issue_id("demo/repo", 1), ref, "demo/repo", s)
    assert res.unresolved is None
    assert res.edge.dst == ids.pr_id("demo/repo", 42)
    assert res.edge.type == EdgeType.MENTIONS
