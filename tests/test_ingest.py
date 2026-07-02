from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import Document, EdgeType, NodeType, RefKind, Reference
from repomind.pipeline.ingest import Ingestor


def _commit_doc(sha, msg, closes=None):
    refs = [Reference(kind=RefKind.PERSON_LOGIN, value="ada", edge=EdgeType.AUTHORED)]
    if closes:
        refs.append(Reference(kind=RefKind.CLOSES_ISSUE, value=str(closes), edge=EdgeType.CLOSES))
    return Document(
        node_id=ids.commit_id(sha),
        node_type=NodeType.COMMIT,
        title=msg,
        repo="demo/repo",
        references=refs,
    )


def _issue_doc(num, title):
    return Document(
        node_id=ids.issue_id("demo/repo", num),
        node_type=NodeType.ISSUE,
        title=title,
        repo="demo/repo",
    )


def test_ingest_creates_nodes_and_resolved_edges():
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    # issue first, then commit that closes it -> edge resolves immediately
    ing.ingest_document(_issue_doc(12, "login bug"))
    ing.ingest_document(_commit_doc("abc", "fix login", closes=12))
    assert store.has_node(ids.person_id("ada"))
    edges = {(e.src, e.dst, e.type.value) for e in store.all_edges()}
    assert (ids.person_id("ada"), ids.commit_id("abc"), "authored") in edges
    assert (ids.commit_id("abc"), ids.issue_id("demo/repo", 12), "closes") in edges


def test_parked_reference_resolves_after_target_arrives():
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    # commit references issue 12 BEFORE the issue exists -> parked
    ing.ingest_document(_commit_doc("abc", "fix login", closes=12))
    assert ing.unresolved_count == 1
    # now the issue arrives -> the parked closes edge should resolve
    ing.ingest_document(_issue_doc(12, "login bug"))
    assert ing.unresolved_count == 0
    edges = {(e.src, e.dst, e.type.value) for e in store.all_edges()}
    assert (ids.commit_id("abc"), ids.issue_id("demo/repo", 12), "closes") in edges


def test_ingest_is_idempotent():
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    ing.ingest_document(_issue_doc(12, "login bug"))
    ing.ingest_document(_commit_doc("abc", "fix login", closes=12))
    counts1 = store.counts()
    # re-ingest identical docs -> no growth
    ing.ingest_document(_issue_doc(12, "login bug"))
    ing.ingest_document(_commit_doc("abc", "fix login", closes=12))
    assert store.counts() == counts1


def test_deletion_tombstones_and_preserves_history():
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    fid = ids.file_id("demo/repo", "auth.py")
    ing.ingest_document(Document(node_id=fid, node_type=NodeType.FILE, title="auth.py", repo="demo/repo"))
    ing.ingest_document(
        Document(
            node_id=fid,
            node_type=NodeType.FILE,
            title="auth.py",
            repo="demo/repo",
            attributes={"deleted_in": "abc"},
            deleted=True,
        )
    )
    node = store.get_node(fid)
    assert node is not None  # preserved
    assert node.status == "deleted"
    assert node.deleted_in == "abc"
