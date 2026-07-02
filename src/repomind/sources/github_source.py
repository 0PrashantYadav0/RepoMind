"""GitHubSource: ingest pull requests, issues, reviewers and authors via the
GitHub API. Uses PyGithub for the real path, but accepts an injectable repo
handle (duck-typed) so the connector is fully unit-testable offline.

The repo handle must provide:
    .get_pulls(state="all") -> iterable of PR-like objects
    .get_issues(state="all") -> iterable of issue-like objects
PR-like / issue-like objects expose: number, title, body, state, created_at,
updated_at, user.login, and (for PRs) get_reviews() and (optionally)
.pull_request marker on issues to distinguish them.
"""
from __future__ import annotations

import re
from typing import Iterable

from repomind import ids
from repomind.models import Document, EdgeType, NodeType, RefKind, Reference

_CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_ISSUE_RE = re.compile(r"#(\d+)")
_MENTION_RE = re.compile(r"@([A-Za-z0-9-]+)")


class GitHubSource:
    name = "github"

    def __init__(
        self,
        gh_repo,
        repo_name: str,
        max_prs: int | None = None,
        max_issues: int | None = None,
    ) -> None:
        self._repo = gh_repo
        self.repo_name = repo_name
        self.max_prs = max_prs
        self.max_issues = max_issues

    @classmethod
    def from_token(
        cls,
        token: str,
        repo_name: str,
        max_prs: int | None = None,
        max_issues: int | None = None,
    ) -> "GitHubSource":
        from github import Github  # lazy: PyGithub only needed for the real path

        gh = Github(token)
        return cls(gh.get_repo(repo_name), repo_name, max_prs, max_issues)

    def fetch(self, since: str | None = None) -> Iterable[Document]:
        yield from self._fetch_pulls()
        yield from self._fetch_issues()

    # -- pull requests -------------------------------------------------------
    def _fetch_pulls(self) -> Iterable[Document]:
        count = 0
        for pr in self._repo.get_pulls(state="all"):
            if self.max_prs and count >= self.max_prs:
                break
            count += 1
            body = pr.body or ""
            author = getattr(getattr(pr, "user", None), "login", None)
            refs: list[Reference] = []
            if author:
                refs.append(Reference(kind=RefKind.PERSON_LOGIN, value=author, edge=EdgeType.AUTHORED))
            for num in _CLOSES_RE.findall(body):
                refs.append(Reference(kind=RefKind.CLOSES_ISSUE, value=num, edge=EdgeType.CLOSES))
            for num in _ISSUE_RE.findall(body):
                refs.append(Reference(kind=RefKind.ISSUE_NUMBER, value=num, edge=EdgeType.MENTIONS))
            for login in _MENTION_RE.findall(body):
                refs.append(Reference(kind=RefKind.PERSON_LOGIN, value=login, edge=EdgeType.MENTIONS))
            # Reviewers.
            get_reviews = getattr(pr, "get_reviews", None)
            if callable(get_reviews):
                for review in get_reviews():
                    reviewer = getattr(getattr(review, "user", None), "login", None)
                    if reviewer:
                        refs.append(
                            Reference(kind=RefKind.PERSON_LOGIN, value=reviewer, edge=EdgeType.REVIEWED)
                        )

            yield Document(
                node_id=ids.pr_id(self.repo_name, pr.number),
                node_type=NodeType.PULL_REQUEST,
                title=pr.title or f"PR #{pr.number}",
                body=body,
                repo=self.repo_name,
                author_login=author,
                created_at=getattr(pr, "created_at", None),
                updated_at=getattr(pr, "updated_at", None),
                attributes={"number": pr.number, "state": getattr(pr, "state", "unknown")},
                references=refs,
            )

    # -- issues --------------------------------------------------------------
    def _fetch_issues(self) -> Iterable[Document]:
        count = 0
        for issue in self._repo.get_issues(state="all"):
            if self.max_issues and count >= self.max_issues:
                break
            # PyGithub returns PRs as issues too; skip those (we ingest PRs above).
            if getattr(issue, "pull_request", None):
                continue
            count += 1
            body = issue.body or ""
            author = getattr(getattr(issue, "user", None), "login", None)
            refs: list[Reference] = []
            if author:
                refs.append(Reference(kind=RefKind.PERSON_LOGIN, value=author, edge=EdgeType.AUTHORED))
            for login in _MENTION_RE.findall(body):
                refs.append(Reference(kind=RefKind.PERSON_LOGIN, value=login, edge=EdgeType.MENTIONS))

            yield Document(
                node_id=ids.issue_id(self.repo_name, issue.number),
                node_type=NodeType.ISSUE,
                title=issue.title or f"Issue #{issue.number}",
                body=body,
                repo=self.repo_name,
                author_login=author,
                created_at=getattr(issue, "created_at", None),
                updated_at=getattr(issue, "updated_at", None),
                attributes={"number": issue.number, "state": getattr(issue, "state", "unknown")},
                references=refs,
            )
