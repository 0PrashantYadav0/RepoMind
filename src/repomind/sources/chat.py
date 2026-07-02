"""Shared chat-message normalization used by every chat source (Discord export,
Slack bot, Discord bot, and the n8n low-code path). One place to turn a Message
into a Document, so every chat connector behaves identically (DRY).
"""
from __future__ import annotations

import re
from datetime import datetime

from repomind import ids
from repomind.models import Document, EdgeType, Message, NodeType, RefKind, Reference

_ISSUE_RE = re.compile(r"#(\d+)")
_URL_RE = re.compile(r"https?://\S+")


def message_to_document(msg: Message, repo_name: str) -> Document:
    """Normalize a chat Message into a Message Document with references.

    Author -> authored edge; #N references -> discussed-in (chat <-> code bridge).
    """
    refs: list[Reference] = [
        Reference(kind=RefKind.PERSON_LOGIN, value=msg.author, edge=EdgeType.AUTHORED),
    ]
    for num in _ISSUE_RE.findall(msg.text):
        refs.append(Reference(kind=RefKind.ISSUE_NUMBER, value=num, edge=EdgeType.DISCUSSED_IN))

    preview = msg.text if len(msg.text) <= 80 else msg.text[:77] + "..."
    return Document(
        node_id=ids.message_id(msg.message_id),
        node_type=NodeType.MESSAGE,
        title=f"{msg.author} in #{msg.channel}: {preview}",
        body=msg.text,
        repo=repo_name,
        author_login=msg.author,
        created_at=msg.timestamp,
        attributes={"channel": msg.channel, "thread_id": msg.thread_id, "links": msg.links},
        references=refs,
    )


def message_from_dict(data: dict) -> Message:
    """Build a Message from a loose dict (used by the n8n / generic ingest path).

    Accepts: message_id (or id), author, text (or content), channel, thread_id,
    timestamp (iso8601), links.
    """
    text = data.get("text") or data.get("content") or ""
    ts = data.get("timestamp")
    when: datetime | None = None
    if isinstance(ts, str) and ts:
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            when = None
    elif isinstance(ts, datetime):
        when = ts
    links = data.get("links")
    if links is None:
        links = _URL_RE.findall(text)
    return Message(
        message_id=str(data.get("message_id") or data.get("id") or ""),
        author=data.get("author") or "unknown",
        timestamp=when,
        channel=data.get("channel", ""),
        thread_id=data.get("thread_id"),
        text=text,
        links=links,
    )
