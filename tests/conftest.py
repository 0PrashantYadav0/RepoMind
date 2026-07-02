"""Shared test fixtures: a throwaway git repo, a fake GitHub repo handle, and a
Discord export file. All offline, no network or API keys.
"""
from __future__ import annotations

import json

import pytest

from tests.fakes import (
    API_TOKEN,
    AUTH_HEADERS,
    FakeIssue,
    FakePull,
    FakeReview,
    FakeUser,
    make_github_source,
)


@pytest.fixture(autouse=True)
def _api_token(monkeypatch):
    """The server requires an API key. Configure one for every test by default;
    individual tests can override (delenv) to assert the fail-closed behavior.

    Also keep tests hermetic: never read the developer's real .env, and clear
    any real secrets from the environment so offline tests can't reach out to
    GitHub / Cognee Cloud.
    """
    monkeypatch.setattr("repomind.config.load_dotenv", lambda *a, **k: False)
    for var in ("GITHUB_TOKEN", "COGNEE_API_KEY", "COGNEE_SERVICE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REPOMIND_API_TOKEN", API_TOKEN)


@pytest.fixture
def auth_headers():
    return dict(AUTH_HEADERS)


@pytest.fixture
def git_repo(tmp_path):
    """Create a tiny real git repo with a few commits referencing issues."""
    from git import Actor, Repo

    path = tmp_path / "demo_repo"
    path.mkdir()
    repo = Repo.init(path)
    author = Actor("Ada Lovelace", "ada@example.com")

    def write_commit(filename, content, message):
        f = path / filename
        f.write_text(content)
        repo.index.add([str(f)])
        repo.index.commit(message, author=author, committer=author)

    write_commit("auth.py", "def login():\n    pass\n", "Add auth module")
    write_commit("auth.py", "def login():\n    return True\n", "Fix login bug, closes #12")
    write_commit("db.py", "DB = {}\n", "Add db layer (see #7)")
    return {"path": str(path), "name": "demo/repo", "repo": repo}


@pytest.fixture
def fake_github_repo():
    pulls = [
        FakePull(
            number=12,
            title="Fix login bug",
            body="Closes #7. Reviewed work by @grace.",
            user=FakeUser("ada"),
            state="closed",
            merged=True,
            _reviews=[FakeReview(FakeUser("grace"))],
        ),
    ]
    issues = [
        FakeIssue(number=7, title="Login returns None", body="Auth is broken cc @ada", user=FakeUser("grace")),
        # A PR shows up in get_issues too; must be skipped by the source.
        FakeIssue(number=12, title="Fix login bug", body="", user=FakeUser("ada"), pull_request=object()),
    ]
    return make_github_source(pulls, issues)


@pytest.fixture
def discord_export(tmp_path):
    data = {
        "channel": {"id": "1", "name": "dev"},
        "messages": [
            {
                "id": "100",
                "timestamp": "2026-01-01T10:00:00.000+00:00",
                "author": {"name": "ada", "nickname": "Ada"},
                "content": "I think the login bug is #12, let's discuss",
            },
            {
                "id": "101",
                "timestamp": "2026-01-01T10:05:00.000+00:00",
                "author": {"name": "grace"},
                "content": "Agreed, see https://example.com/spec",
            },
        ],
    }
    p = tmp_path / "export.json"
    p.write_text(json.dumps(data))
    return str(p)


@pytest.fixture
def base_config(tmp_path, git_repo):
    from repomind.config import Config, MemoryConfig, RepoConfig, StateConfig

    return Config(
        repo=RepoConfig(name="demo/repo", local_path=git_repo["path"]),
        memory=MemoryConfig(backend="memory"),
        state=StateConfig(db_path=str(tmp_path / "state.sqlite3")),
    )
