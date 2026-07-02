from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import NodeType
from repomind.pipeline.ingest import Ingestor


def test_github_source_skips_prs_in_issue_list(fake_github_repo):
    docs = list(fake_github_repo.fetch())
    issues = [d for d in docs if d.node_type == NodeType.ISSUE]
    prs = [d for d in docs if d.node_type == NodeType.PULL_REQUEST]
    assert len(prs) == 1
    assert len(issues) == 1  # PR-as-issue (#12) was skipped
    assert issues[0].attributes["number"] == 7


def test_github_source_builds_review_and_closes_edges(fake_github_repo):
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    ing.ingest_documents(fake_github_repo.fetch())
    edges = {(e.src, e.dst, e.type.value) for e in store.all_edges()}
    pr12 = ids.pr_id("demo/repo", 12)
    iss7 = ids.issue_id("demo/repo", 7)
    # ada authored the PR
    assert (ids.person_id("ada"), pr12, "authored") in edges
    # grace reviewed the PR
    assert (ids.person_id("grace"), pr12, "reviewed") in edges
    # PR closes issue 7
    assert (pr12, iss7, "closes") in edges
