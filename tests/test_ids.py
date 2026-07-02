from repomind import ids


def test_ids_are_deterministic_and_normalized():
    assert ids.commit_id("ABC123") == ids.commit_id("abc123")
    assert ids.pr_id("Demo/Repo", 12) == ids.pr_id("demo/repo", "12")
    assert ids.issue_id("demo/repo", 7) == "github:issue:demo/repo:7"
    assert ids.person_id("Ada") == ids.person_id("ada")
    assert ids.file_id("demo/repo", "/src/auth.py") == "git:file:demo/repo:src/auth.py"


def test_distinct_entities_get_distinct_ids():
    assert ids.pr_id("demo/repo", 12) != ids.issue_id("demo/repo", 12)
    assert ids.file_id("demo/repo", "a.py") != ids.module_id("demo/repo", "a.py")
