from repomind import ids
from repomind.engine import Engine


def test_engine_backfill_git_and_github(base_config, fake_github_repo):
    eng = Engine(base_config)
    eng.set_github_source(fake_github_repo)
    eng.backfill_git()
    eng.backfill_github()
    counts = eng.counts()
    assert counts["by_type"]["Commit"] == 3
    assert counts["by_type"]["PullRequest"] == 1
    assert counts["by_type"]["Issue"] == 1
    # cross-source resolution: the git commit "closes #12" and PR "closes #7"
    assert eng.ingestor.unresolved_count == 0
    eng.close()


def test_engine_webhook_idempotent(base_config):
    eng = Engine(base_config)
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 99,
            "title": "New feature",
            "body": "",
            "user": {"login": "ada"},
            "state": "open",
        },
        "repository": {"full_name": "demo/repo"},
    }
    r1 = eng.handle_webhook("pull_request", payload, "guid-1")
    assert r1["status"] == "ok" and r1["ingested"] == 1
    r2 = eng.handle_webhook("pull_request", payload, "guid-1")
    assert r2["status"] == "duplicate" and r2["ingested"] == 0
    assert eng.store.has_node(ids.pr_id("demo/repo", 99))
    eng.close()


def test_full_sync_reconcile_tombstones_vanished_pr(base_config):
    from tests.fakes import FakePull, FakeUser, make_github_source

    # First sync: two PRs present upstream.
    src_v1 = make_github_source(
        pulls=[
            FakePull(1, "PR one", "", FakeUser("ada")),
            FakePull(2, "PR two", "", FakeUser("grace")),
        ],
        issues=[],
    )
    eng = Engine(base_config)
    eng.set_github_source(src_v1)
    eng.sync(scope="prs", mode="full")
    assert eng.store.get_node(ids.pr_id("demo/repo", 2)).status == "active"

    # Second full sync: PR #2 has disappeared upstream -> must be tombstoned.
    src_v2 = make_github_source(pulls=[FakePull(1, "PR one", "", FakeUser("ada"))], issues=[])
    eng.set_github_source(src_v2)
    report = eng.sync(scope="prs", mode="full")
    assert report["tombstoned"] == 1
    assert eng.store.get_node(ids.pr_id("demo/repo", 2)).status == "deleted"
    assert eng.store.get_node(ids.pr_id("demo/repo", 1)).status == "active"
    eng.close()


def test_verify_reports_consistency(base_config, fake_github_repo):
    eng = Engine(base_config)
    eng.set_github_source(fake_github_repo)
    eng.backfill_git()
    eng.backfill_github()
    report = eng.verify(scope="all")
    assert report["consistent"] is True
    assert report["unresolved_references"] == []
    eng.close()


def test_forget_hard_deletes(base_config):
    eng = Engine(base_config)
    eng.backfill_git()
    person = ids.person_id("Ada Lovelace")
    assert eng.store.has_node(person)
    assert eng.forget(person) is True
    assert not eng.store.has_node(person)
    eng.close()
