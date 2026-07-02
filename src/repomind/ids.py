"""Deterministic, collision-free stable IDs for every entity in the graph.

The same real-world entity must always map to the same ID so that re-processing
(via webhook, poller, or manual sync) is an idempotent upsert, never a duplicate.
"""
from __future__ import annotations


def _norm_repo(repo: str) -> str:
    """Normalize a repo identifier like 'owner/name' (case-insensitive)."""
    return repo.strip().lower()


def commit_id(sha: str) -> str:
    return f"git:commit:{sha.strip().lower()}"


def file_id(repo: str, path: str) -> str:
    return f"git:file:{_norm_repo(repo)}:{path.strip().lstrip('/')}"


def module_id(repo: str, path: str) -> str:
    return f"git:module:{_norm_repo(repo)}:{path.strip().strip('/')}"


def pr_id(repo: str, number: int | str) -> str:
    return f"github:pr:{_norm_repo(repo)}:{int(number)}"


def issue_id(repo: str, number: int | str) -> str:
    return f"github:issue:{_norm_repo(repo)}:{int(number)}"


def person_id(login: str) -> str:
    return f"person:{login.strip().lower()}"


def message_id(message_id_value: str) -> str:
    return f"discord:msg:{str(message_id_value).strip()}"


def decision_id(repo: str, slug: str) -> str:
    return f"adr:{_norm_repo(repo)}:{slug.strip().lower()}"
