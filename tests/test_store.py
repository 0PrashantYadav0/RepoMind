from repomind.graph.store import InMemoryGraphStore
from repomind.models import Edge, EdgeType, Node, NodeType


def make_store():
    s = InMemoryGraphStore()
    s.upsert_node(Node(id="p:ada", type=NodeType.PERSON, title="ada"))
    s.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    s.upsert_node(Node(id="iss:7", type=NodeType.ISSUE, title="Login broken"))
    s.upsert_edge(Edge(src="p:ada", dst="pr:1", type=EdgeType.AUTHORED))
    s.upsert_edge(Edge(src="pr:1", dst="iss:7", type=EdgeType.CLOSES))
    return s


def test_upsert_is_idempotent():
    s = make_store()
    before = s.counts()
    s.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    s.upsert_edge(Edge(src="p:ada", dst="pr:1", type=EdgeType.AUTHORED))
    assert s.counts() == before


def test_upsert_merges_attributes():
    s = make_store()
    s.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="", attributes={"state": "merged"}))
    node = s.get_node("pr:1")
    assert node.title == "Fix login"  # not clobbered by empty title
    assert node.attributes["state"] == "merged"


def test_tombstone_preserves_node_and_excludes_from_search():
    s = make_store()
    assert s.tombstone_node("pr:1", deleted_in="abc")
    node = s.get_node("pr:1")
    assert node.status == "deleted"
    assert node.deleted_in == "abc"
    assert all(n.id != "pr:1" for n in s.search("login"))
    assert any(n.id == "pr:1" for n in s.search("login", include_deleted=True))


def test_hard_delete_removes_node_and_edges():
    s = make_store()
    assert s.hard_delete("pr:1")
    assert s.get_node("pr:1") is None
    assert all("pr:1" not in (e.src, e.dst) for e in s.all_edges())


def test_neighbors_directions():
    s = make_store()
    out = s.neighbors("pr:1", direction="out")
    assert {n.id for _, n in out} == {"iss:7"}
    inc = s.neighbors("pr:1", direction="in")
    assert {n.id for _, n in inc} == {"p:ada"}


def test_persistence_roundtrip(tmp_path):
    s = make_store()
    path = tmp_path / "g.json"
    s.save(path)
    s2 = InMemoryGraphStore()
    s2.load(path)
    assert s2.counts()["nodes"] == s.counts()["nodes"]
    assert s2.counts()["edges"] == s.counts()["edges"]
