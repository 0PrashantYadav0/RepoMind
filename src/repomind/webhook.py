"""GitHub webhook handling: HMAC signature verification and translation of
webhook payloads into normalized Documents that flow through the SAME ingest
pipeline as backfill (one code path = correctness).
"""
from __future__ import annotations

import hashlib
import hmac
import re

from repomind import ids
from repomind.models import Document, EdgeType, NodeType, RefKind, Reference

_CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_ISSUE_RE = re.compile(r"#(\d+)")
_MENTION_RE = re.compile(r"@([A-Za-z0-9-]+)")


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Verify the X-Hub-Signature-256 header against the raw body."""
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _refs_from_text(text: str, *, include_closes: bool = True) -> list[Reference]:
    refs: list[Reference] = []
    if include_closes:
        for num in _CLOSES_RE.findall(text):
            refs.append(Reference(kind=RefKind.CLOSES_ISSUE, value=num, edge=EdgeType.CLOSES))
    for num in _ISSUE_RE.findall(text):
        refs.append(Reference(kind=RefKind.ISSUE_NUMBER, value=num, edge=EdgeType.MENTIONS))
    for login in _MENTION_RE.findall(text):
        refs.append(Reference(kind=RefKind.PERSON_LOGIN, value=login, edge=EdgeType.MENTIONS))
    return refs


def event_to_documents(event_type: str, payload: dict, repo_name: str) -> list[Document]:
    repo = repo_name or (payload.get("repository") or {}).get("full_name", "")
    if event_type == "pull_request":
        return _pull_request_docs(payload, repo)
    if event_type == "issues":
        return _issue_docs(payload, repo)
    if event_type == "push":
        return _push_docs(payload, repo)
    return []


def _pull_request_docs(payload: dict, repo: str) -> list[Document]:
    pr = payload.get("pull_request") or {}
    number = pr.get("number")
    if number is None:
        return []
    body = pr.get("body") or ""
    author = (pr.get("user") or {}).get("login")
    refs: list[Reference] = []
    if author:
        refs.append(Reference(kind=RefKind.PERSON_LOGIN, value=author, edge=EdgeType.AUTHORED))
    refs += _refs_from_text(body)
    state = "merged" if pr.get("merged") else pr.get("state", "open")
    return [
        Document(
            node_id=ids.pr_id(repo, number),
            node_type=NodeType.PULL_REQUEST,
            title=pr.get("title") or f"PR #{number}",
            body=body,
            repo=repo,
            author_login=author,
            attributes={"number": number, "state": state, "action": payload.get("action")},
            references=refs,
        )
    ]


def _issue_docs(payload: dict, repo: str) -> list[Document]:
    issue = payload.get("issue") or {}
    number = issue.get("number")
    if number is None:
        return []
    body = issue.get("body") or ""
    author = (issue.get("user") or {}).get("login")
    action = payload.get("action")
    refs: list[Reference] = []
    if author:
        refs.append(Reference(kind=RefKind.PERSON_LOGIN, value=author, edge=EdgeType.AUTHORED))
    refs += _refs_from_text(body, include_closes=False)
    # "deleted" action -> tombstone (history-preserving).
    deleted = action == "deleted"
    return [
        Document(
            node_id=ids.issue_id(repo, number),
            node_type=NodeType.ISSUE,
            title=issue.get("title") or f"Issue #{number}",
            body=body,
            repo=repo,
            author_login=author,
            attributes={"number": number, "state": issue.get("state", "open"), "action": action},
            references=refs,
            deleted=deleted,
        )
    ]


def _push_docs(payload: dict, repo: str) -> list[Document]:
    docs: list[Document] = []
    for commit in payload.get("commits", []):
        sha = commit.get("id")
        if not sha:
            continue
        message = commit.get("message", "")
        title = message.splitlines()[0] if message else f"commit {sha[:7]}"
        author = (commit.get("author") or {}).get("username") or (commit.get("author") or {}).get("name")
        refs: list[Reference] = []
        if author:
            refs.append(Reference(kind=RefKind.PERSON_LOGIN, value=author, edge=EdgeType.AUTHORED))
        refs += _refs_from_text(message)
        for path in commit.get("modified", []) + commit.get("added", []):
            refs.append(Reference(kind=RefKind.FILE_PATH, value=path, edge=EdgeType.MODIFIES))
        docs.append(
            Document(
                node_id=ids.commit_id(sha),
                node_type=NodeType.COMMIT,
                title=title,
                body=message,
                repo=repo,
                author_login=author,
                attributes={"sha": sha, "short_sha": sha[:7]},
                references=refs,
            )
        )
        # Files removed in this push -> tombstone (history-preserving deletion).
        for path in commit.get("removed", []):
            docs.append(
                Document(
                    node_id=ids.file_id(repo, path),
                    node_type=NodeType.FILE,
                    title=path,
                    repo=repo,
                    attributes={"path": path, "deleted_in": sha},
                    deleted=True,
                )
            )
    return docs
