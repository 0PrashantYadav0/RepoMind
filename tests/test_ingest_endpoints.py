"""Phase 2 Option C: the n8n / low-code ingest endpoint and the generic
ingest_source engine path."""
from fastapi.testclient import TestClient

from repomind import ids
from repomind.api import create_app
from repomind.engine import Engine
from tests.fakes import AUTH_HEADERS


def test_ingest_message_endpoint(base_config):
    eng = Engine(base_config)
    # Seed the issue so the discussed-in edge resolves.
    from repomind.models import Node, NodeType

    eng.store.upsert_node(Node(id=ids.issue_id("demo/repo", 12), type=NodeType.ISSUE, title="bug"))
    client = TestClient(create_app(engine=eng), headers=AUTH_HEADERS)

    r = client.post(
        "/ingest/message",
        json={"id": "555", "author": "ada", "content": "tracking #12", "channel": "dev"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["ingested"] == 1
    assert eng.store.has_node(ids.message_id("555"))
    edges = {(e.src, e.dst, e.type.value) for e in eng.store.all_edges()}
    assert (ids.issue_id("demo/repo", 12), ids.message_id("555"), "discussed-in") in edges


def test_ingest_message_missing_id(base_config):
    eng = Engine(base_config)
    client = TestClient(create_app(engine=eng), headers=AUTH_HEADERS)
    r = client.post("/ingest/message", json={"author": "ada", "content": "no id here"})
    assert r.status_code == 200
    assert r.json()["status"] == "error"


def test_ingest_source_generic(base_config):
    """The generic Phase 2 ingest_source path works for any Source."""
    from tests.fakes import FakeDiscordAuthor, FakeDiscordChannel, FakeDiscordMessage
    from repomind.sources.discord_bot_source import DiscordBotSource

    eng = Engine(base_config)
    channels = [
        FakeDiscordChannel(
            "dev",
            [FakeDiscordMessage(id=1, author=FakeDiscordAuthor("ada"), content="hello world")],
        )
    ]
    n = eng.ingest_source(DiscordBotSource(channels, "demo/repo"))
    assert n == 1
    assert eng.store.has_node(ids.message_id("1"))
    eng.close()
