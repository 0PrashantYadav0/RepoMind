"""DiscordBotSource (Phase 2): live Discord ingestion via a gateway bot.

Mirrors DiscordExportSource output so downstream code is unchanged. Two modes:
  - BACKFILL: paginate channel.history(after=cursor) for configured channels.
  - LIVE TAIL: translate an on_message gateway event into a Document.

The Discord client/channels are injectable (duck-typed) for offline tests. The
real bot (discord.py) is lazy-imported in build_bot. Required gateway intents:
MESSAGE_CONTENT (privileged), Guilds, Guild Messages.
"""
from __future__ import annotations

from typing import Iterable

from repomind.models import Document, Message
from repomind.sources.chat import message_to_document


def discord_message_to_message(raw, channel_name: str) -> Message:
    """Normalize a discord.py-style message object (duck-typed) into Message.

    Expects attributes: id, author (with .name/.display_name), content,
    created_at, and optionally reference.message_id / thread.
    """
    author = getattr(raw, "author", None)
    name = getattr(author, "display_name", None) or getattr(author, "name", None) or "unknown"
    ref = getattr(raw, "reference", None)
    thread_id = getattr(ref, "message_id", None) if ref else None
    return Message(
        message_id=str(getattr(raw, "id", "")),
        author=name,
        timestamp=getattr(raw, "created_at", None),
        channel=channel_name,
        thread_id=str(thread_id) if thread_id else None,
        text=getattr(raw, "content", "") or "",
    )


class DiscordBotSource:
    name = "discord-bot"

    def __init__(self, channels, repo_name: str) -> None:
        # channels: iterable of objects with .name and
        # .history(after=None) -> iterable of message objects.
        self._channels = channels
        self.repo_name = repo_name

    def fetch(self, since: str | None = None) -> Iterable[Document]:
        for channel in self._channels:
            channel_name = getattr(channel, "name", "")
            for raw in channel.history(after=since):
                yield message_to_document(
                    discord_message_to_message(raw, channel_name), self.repo_name
                )

    def message_to_document(self, raw, channel_name: str) -> Document:
        """Translate a single live on_message event into a Document."""
        return message_to_document(
            discord_message_to_message(raw, channel_name), self.repo_name
        )
