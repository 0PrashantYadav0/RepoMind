"""Deterministic reference resolution.

Turns a Document's References into concrete Edges against stable IDs. Identity-
bearing targets (people, files, modules) are created on demand because the
reference IS their identity. Numeric issue/PR references are NEVER guessed: if
the target node does not exist yet, the reference is parked as Unresolved and
retried after later ingests, so an edge is never created against a wrong target.
"""
from __future__ import annotations

from dataclasses import dataclass

from repomind import ids
from repomind.graph.store import GraphStore
from repomind.models import Edge, EdgeType, Node, NodeType, RefKind, Reference, UnresolvedRef

# Edges whose direction is target -> src (instead of the default src -> target).
_REVERSED = {EdgeType.AUTHORED, EdgeType.REVIEWED, EdgeType.DISCUSSED_IN}

# Default edge type when a reference does not specify one.
_DEFAULT_EDGE = {
    RefKind.PERSON_LOGIN: EdgeType.MENTIONS,
    RefKind.FILE_PATH: EdgeType.MENTIONS,
    RefKind.ISSUE_NUMBER: EdgeType.MENTIONS,
    RefKind.PR_NUMBER: EdgeType.MENTIONS,
    RefKind.CLOSES_ISSUE: EdgeType.CLOSES,
}


@dataclass
class ResolveResult:
    edge: Edge | None = None
    new_node: Node | None = None
    unresolved: UnresolvedRef | None = None


def _directed(edge_type: EdgeType, src_id: str, target_id: str) -> tuple[str, str]:
    if edge_type in _REVERSED:
        return target_id, src_id
    return src_id, target_id


def resolve_reference(
    src_id: str, ref: Reference, repo: str, store: GraphStore
) -> ResolveResult:
    edge_type = ref.edge or _DEFAULT_EDGE[ref.kind]

    # -- identity-bearing targets: safe to create on demand ------------------
    if ref.kind == RefKind.PERSON_LOGIN:
        pid = ids.person_id(ref.value)
        new_node = None
        if not store.has_node(pid):
            new_node = Node(id=pid, type=NodeType.PERSON, title=ref.value)
        a, b = _directed(edge_type, src_id, pid)
        return ResolveResult(edge=Edge(src=a, dst=b, type=edge_type), new_node=new_node)

    if ref.kind == RefKind.FILE_PATH:
        if edge_type == EdgeType.PART_OF:
            tid = ids.module_id(repo, ref.value)
            ntype = NodeType.MODULE
        else:
            tid = ids.file_id(repo, ref.value)
            ntype = NodeType.FILE
        new_node = None
        if not store.has_node(tid):
            new_node = Node(id=tid, type=ntype, title=ref.value, attributes={"path": ref.value})
        a, b = _directed(edge_type, src_id, tid)
        return ResolveResult(edge=Edge(src=a, dst=b, type=edge_type), new_node=new_node)

    # -- numeric issue/PR targets: never guessed -----------------------------
    if ref.kind in (RefKind.ISSUE_NUMBER, RefKind.CLOSES_ISSUE):
        issue_tid = ids.issue_id(repo, ref.value)
        pr_tid = ids.pr_id(repo, ref.value)
        target = None
        if store.has_node(issue_tid):
            target = issue_tid
        elif store.has_node(pr_tid):
            target = pr_tid
        if target is None:
            return ResolveResult(unresolved=UnresolvedRef(src=src_id, ref=ref, repo=repo))
        a, b = _directed(edge_type, src_id, target)
        return ResolveResult(edge=Edge(src=a, dst=b, type=edge_type))

    if ref.kind == RefKind.PR_NUMBER:
        pr_tid = ids.pr_id(repo, ref.value)
        if not store.has_node(pr_tid):
            return ResolveResult(unresolved=UnresolvedRef(src=src_id, ref=ref, repo=repo))
        a, b = _directed(edge_type, src_id, pr_tid)
        return ResolveResult(edge=Edge(src=a, dst=b, type=edge_type))

    return ResolveResult(unresolved=UnresolvedRef(src=src_id, ref=ref, repo=repo))
