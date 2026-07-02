"""Shared offline test doubles, duck-typed to what the real connectors need."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from repomind.sources.github_source import GitHubSource

# Shared API token used across the test suite (the server requires one).
API_TOKEN = "test-api-token"
AUTH_HEADERS = {"X-API-Key": API_TOKEN}


@dataclass
class FakeUser:
    login: str


@dataclass
class FakeReview:
    user: FakeUser


@dataclass
class FakePull:
    number: int
    title: str
    body: str
    user: FakeUser
    state: str = "open"
    merged: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _reviews: list = field(default_factory=list)

    def get_reviews(self):
        return list(self._reviews)


@dataclass
class FakeIssue:
    number: int
    title: str
    body: str
    user: FakeUser
    state: str = "open"
    pull_request: object | None = None  # marker; PRs-as-issues set this
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class FakeGitHubRepo:
    def __init__(self, pulls, issues):
        self._pulls = pulls
        self._issues = issues

    def get_pulls(self, state="all"):
        return list(self._pulls)

    def get_issues(self, state="all"):
        return list(self._issues)


def make_github_source(pulls, issues, repo_name="demo/repo") -> GitHubSource:
    return GitHubSource(FakeGitHubRepo(pulls, issues), repo_name)


# -- Slack (Phase 2) ---------------------------------------------------------
class FakeSlackClient:
    """Duck-typed Slack WebClient: paginated conversations_history."""

    def __init__(self, pages_by_channel: dict[str, list[dict]]):
        # pages_by_channel: channel -> list of pages, each page is a response dict
        self._pages = pages_by_channel
        self._idx: dict[str, int] = {}

    def conversations_history(self, channel, cursor=None):
        pages = self._pages.get(channel, [{"messages": []}])
        i = self._idx.get(channel, 0)
        if i >= len(pages):
            return {"messages": []}
        self._idx[channel] = i + 1
        return pages[i]


# -- Discord bot (Phase 2) ---------------------------------------------------
@dataclass
class FakeDiscordAuthor:
    name: str
    display_name: str | None = None


@dataclass
class FakeDiscordMessage:
    id: int
    author: FakeDiscordAuthor
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reference: object | None = None


class FakeDiscordChannel:
    def __init__(self, name, messages):
        self.name = name
        self._messages = messages

    def history(self, after=None):
        return list(self._messages)
