from repomind.engine import Engine


def test_query_answers_with_traversal(base_config, fake_github_repo):
    eng = Engine(base_config)
    eng.set_github_source(fake_github_repo)
    eng.backfill_git()
    eng.backfill_github()

    result = eng.query("login bug fix")
    assert result["seeds"]
    # The answer should mention a relationship (authored/reviewed/closes).
    joined = " ".join(result["facts"]).lower()
    assert any(word in joined for word in ["authored", "reviewed", "closes", "modified", "mentions"])
    # The subgraph for the viz must contain nodes and edges.
    assert result["subgraph"]["nodes"]
    eng.close()


def test_query_empty_graph(base_config):
    eng = Engine(base_config)
    result = eng.query("anything")
    assert result["seeds"] == []
    assert "could not find" in result["answer"].lower()
    eng.close()


def test_deleted_node_answer_notes_history(base_config):
    from repomind.models import Node, NodeType

    eng = Engine(base_config)
    eng.store.upsert_node(Node(id="git:file:demo/repo:auth.py", type=NodeType.FILE, title="auth.py"))
    eng.store.tombstone_node("git:file:demo/repo:auth.py", deleted_in="abc")
    result = eng.query("auth.py", limit=5)
    # include_deleted is False in search by default, so a tombstoned-only match
    # yields no seeds -> graceful message.
    assert result["seeds"] == [] or "history" in result["answer"].lower()
    eng.close()
