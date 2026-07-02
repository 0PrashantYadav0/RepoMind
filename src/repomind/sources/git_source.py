"""GitSource: ingest local git history (commits + the files they modify) via
GitPython. Produces Commit and File documents with authored/modifies edges
expressed as references.
"""
from __future__ import annotations

import re
from typing import Iterable

from repomind import ids
from repomind.models import Document, EdgeType, NodeType, RefKind, Reference

_CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_ISSUE_RE = re.compile(r"#(\d+)")


class GitSource:
    name = "git"

    def __init__(self, repo_path: str, repo_name: str, max_commits: int | None = None) -> None:
        self.repo_path = repo_path
        self.repo_name = repo_name
        self.max_commits = max_commits

    def fetch(self, since: str | None = None) -> Iterable[Document]:
        # Lazy import so importing repomind doesn't require git installed.
        from git import Repo

        repo = Repo(self.repo_path)
        seen_files: set[str] = set()

        rev = None
        if since:
            # Only commits after the cursor sha.
            rev = f"{since}..HEAD"

        commits = repo.iter_commits(rev) if rev else repo.iter_commits()
        count = 0
        for commit in commits:
            if self.max_commits and count >= self.max_commits:
                break
            count += 1
            sha = commit.hexsha
            author_login = (commit.author.name or "unknown").strip()
            message = commit.message if isinstance(commit.message, str) else commit.message.decode()
            title = message.strip().splitlines()[0] if message.strip() else f"commit {sha[:7]}"

            refs: list[Reference] = [
                Reference(kind=RefKind.PERSON_LOGIN, value=author_login, edge=EdgeType.AUTHORED),
            ]
            # Closing references (Fixes #N) -> closes edges.
            for num in _CLOSES_RE.findall(message):
                refs.append(Reference(kind=RefKind.CLOSES_ISSUE, value=num, edge=EdgeType.CLOSES))
            # Plain mentions of issues/PRs.
            for num in _ISSUE_RE.findall(message):
                refs.append(Reference(kind=RefKind.ISSUE_NUMBER, value=num, edge=EdgeType.MENTIONS))

            # Files modified by this commit -> modifies edges + File docs.
            changed_paths = list(commit.stats.files.keys())
            for path in changed_paths:
                refs.append(Reference(kind=RefKind.FILE_PATH, value=path, edge=EdgeType.MODIFIES))

            yield Document(
                node_id=ids.commit_id(sha),
                node_type=NodeType.COMMIT,
                title=title,
                body=message.strip(),
                repo=self.repo_name,
                author_login=author_login,
                created_at=commit.authored_datetime,
                attributes={"sha": sha, "short_sha": sha[:7], "files_changed": len(changed_paths)},
                references=refs,
            )

            # Emit File documents (idempotent; later commits just merge).
            for path in changed_paths:
                fid = ids.file_id(self.repo_name, path)
                if fid in seen_files:
                    continue
                seen_files.add(fid)
                module = path.rsplit("/", 1)[0] if "/" in path else ""
                file_refs: list[Reference] = []
                if module:
                    file_refs.append(
                        Reference(kind=RefKind.FILE_PATH, value=module, edge=EdgeType.PART_OF)
                    )
                yield Document(
                    node_id=fid,
                    node_type=NodeType.FILE,
                    title=path,
                    body="",
                    repo=self.repo_name,
                    attributes={"path": path, "module": module},
                    references=file_refs,
                )
