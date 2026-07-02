from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import EdgeType, Node, NodeType, RefKind, Reference
from repomind.pipeline.resolver import resolve_reference


def test_person_reference_creates_node_and_reversed_edge():
    s = InMemoryGraphStore()
    s.upsert_node(Node(id=ids.commit_id("abc"), type=NodeType.COMMIT, title="c"))
    ref = Reference(kind=RefKind.PERSON_LOGIN, value="Ada", edge=EdgeType.AUTHORED)
    res = resolve_reference(ids.commit_id("abc"), ref, "demo/repo", s)
    assert res.new_node is not None and res.new_node.type == NodeType.PERSON
    # AUTHORED is reversed: person -> commit
    assert res.edge.src == ids.person_id("Ada")
    assert res.edge.dst == ids.commit_id("abc")


def test_numeric_issue_reference_is_parked_when_target_missing():
    s = InMemoryGraphStore()
    s.upsert_node(Node(id=ids.commit_id("abc"), type=NodeType.COMMIT, title="c"))
    ref = Reference(kind=RefKind.CLOSES_ISSUE, value="7", edge=EdgeType.CLOSES)
    res = resolve_reference(ids.commit_id("abc"), ref, "demo/repo", s)
    assert res.edge is None
    assert res.unresolved is not None


def test_numeric_issue_reference_resolves_when_target_present():
    s = InMemoryGraphStore()
    s.upsert_node(Node(id=ids.commit_id("abc"), type=NodeType.COMMIT, title="c"))
    s.upsert_node(Node(id=ids.issue_id("demo/repo", 7), type=NodeType.ISSUE, title="bug"))
    ref = Reference(kind=RefKind.CLOSES_ISSUE, value="7", edge=EdgeType.CLOSES)
    res = resolve_reference(ids.commit_id("abc"), ref, "demo/repo", s)
    assert res.unresolved is None
    assert res.edge.type == EdgeType.CLOSES
    assert res.edge.dst == ids.issue_id("demo/repo", 7)


def test_file_path_part_of_creates_module():
    s = InMemoryGraphStore()
    s.upsert_node(Node(id=ids.file_id("demo/repo", "src/a.py"), type=NodeType.FILE, title="src/a.py"))
    ref = Reference(kind=RefKind.FILE_PATH, value="src", edge=EdgeType.PART_OF)
    res = resolve_reference(ids.file_id("demo/repo", "src/a.py"), ref, "demo/repo", s)
    assert res.new_node.type == NodeType.MODULE
    assert res.edge.type == EdgeType.PART_OF
