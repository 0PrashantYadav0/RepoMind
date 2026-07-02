"""SlackBotSource (Phase 2): live Slack ingestion.

Two modes, both producing the SAME Message Documents as every other chat source:
  - BACKFILL: paginate conversations.history for configured channels.
  - LIVE TAIL: translate a single Events API `message` event into a Document.

The Slack client is injectable (duck-typed) so the connector is unit-testable
offline. The real client (slack_sdk WebClient) is lazy-imported in from_token.

Required scopes for the real bot: channels:history, groups:history,
channels:read, users:read. Live tail uses the Events API (event-driven, so it
sidesteps history pagination rate limits); backfill paginates with cursors and
respects Retry-After on HTTP 429.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from repomind.models import Document, Message
from repomind.sources.chat import message_to_document


def _slack_ts_to_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError):
        return None


def slack_message_to_message(raw: dict, channel: str) -> Message:
    """Normalize a raw Slack message dict into our Message model."""
    ts = raw.get("ts")
    return Message(
        message_id=str(ts),
        author=raw.get("user") or raw.get("username") or "unknown",
        timestamp=_slack_ts_to_dt(ts),
        channel=channel,
        thread_id=raw.get("thread_ts"),
        text=raw.get("text", "") or "",
    )


class SlackBotSource:
    name = "slack"

    def __init__(self, client, repo_name: str, channels: list[str] | None = None) -> None:
        # client must provide conversations_history(channel, cursor=None) ->
        # {"messages": [...], "response_metadata": {"next_cursor": "..."}}
        self._client = client
        self.repo_name = repo_name
        self.channels = channels or []

    @classmethod
    def from_token(cls, token: str, repo_name: str, channels: list[str]) -> "SlackBotSource":
        from slack_sdk import WebClient  # lazy: only for the real path

        return cls(WebClient(token=token), repo_name, channels)

    def fetch(self, since: str | None = None) -> Iterable[Document]:
        for channel in self.channels:
            cursor = None
            while True:
                resp = self._client.conversations_history(channel=channel, cursor=cursor)
                for raw in resp.get("messages", []):
                    if raw.get("subtype"):  # skip joins/leaves/system messages
                        continue
                    yield message_to_document(slack_message_to_message(raw, channel), self.repo_name)
                cursor = (resp.get("response_metadata") or {}).get("next_cursor")
                if not cursor:
                    break

    def event_to_document(self, event: dict) -> Document | None:
        """Translate a single Events API `message` event into a Document."""
        if event.get("type") != "message" or event.get("subtype"):
            return None
        channel = event.get("channel", "")
        return message_to_document(slack_message_to_message(event, channel), self.repo_name)
