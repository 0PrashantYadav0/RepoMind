from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import NodeType
from repomind.pipeline.ingest import Ingestor
from repomind.sources.git_source import GitSource


def test_git_source_emits_commits_and_files(git_repo):
    src = GitSource(git_repo["path"], git_repo["name"])
    docs = list(src.fetch())
    commits = [d for d in docs if d.node_type == NodeType.COMMIT]
    files = [d for d in docs if d.node_type == NodeType.FILE]
    assert len(commits) == 3
    assert {f.title for f in files} == {"auth.py", "db.py"}
    # the "closes #12" commit carries a CLOSES reference
    closing = [d for d in commits if "closes #12" in d.body.lower()]
    assert closing and any(r.value == "12" for r in closing[0].references)


def test_git_source_ingests_into_graph(git_repo):
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    src = GitSource(git_repo["path"], git_repo["name"])
    ing.ingest_documents(src.fetch())
    # Ada authored commits
    assert store.has_node(ids.person_id("Ada Lovelace"))
    counts = store.counts()
    assert counts["by_type"]["Commit"] == 3
    assert counts["by_type"]["File"] == 2
    assert counts["by_type"]["Person"] >= 1
