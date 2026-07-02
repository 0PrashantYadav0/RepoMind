"""DiscordExportSource: ingest a static Discord chat export (the JSON produced
by DiscordChatExporter). Messages become Message nodes; references to issues/PRs
(#123) become discussed-in edges, linking chat to code decisions.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from repomind.models import Document, Message
from repomind.sources.chat import message_to_document

_URL_RE = re.compile(r"https?://\S+")


def parse_export(path: str | Path) -> tuple[str, list[Message]]:
    """Parse a DiscordChatExporter JSON file into (channel_name, messages)."""
    data = json.loads(Path(path).read_text())
    channel = (data.get("channel") or {}).get("name", "")
    out: list[Message] = []
    for m in data.get("messages", []):
        author = m.get("author") or {}
        name = author.get("nickname") or author.get("name") or "unknown"
        ts = m.get("timestamp")
        when: datetime | None = None
        if ts:
            try:
                when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                when = None
        content = m.get("content", "") or ""
        out.append(
            Message(
                message_id=str(m.get("id")),
                author=name,
                timestamp=when,
                channel=channel,
                thread_id=(m.get("reference") or {}).get("messageId"),
                text=content,
                links=_URL_RE.findall(content),
            )
        )
    return channel, out


class DiscordExportSource:
    name = "discord-export"

    def __init__(self, export_path: str, repo_name: str) -> None:
        self.export_path = export_path
        self.repo_name = repo_name

    def fetch(self, since: str | None = None) -> Iterable[Document]:
        _, messages = parse_export(self.export_path)
        for msg in messages:
            yield message_to_document(msg, self.repo_name)
