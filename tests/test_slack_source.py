from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import Node, NodeType
from repomind.pipeline.ingest import Ingestor
from repomind.sources.slack_source import SlackBotSource
from tests.fakes import FakeSlackClient


def _client():
    return FakeSlackClient(
        {
            "C1": [
                {
                    "messages": [
                        {"ts": "1700000000.000100", "user": "ada", "text": "looking at #12"},
                        {"ts": "1700000001.000200", "user": "grace", "text": "joined", "subtype": "channel_join"},
                    ],
                    "response_metadata": {"next_cursor": "page2"},
                },
                {
                    "messages": [
                        {"ts": "1700000002.000300", "user": "grace", "text": "fixed it"},
                    ],
                    "response_metadata": {"next_cursor": ""},
                },
            ]
        }
    )


def test_slack_backfill_paginates_and_skips_subtypes():
    src = SlackBotSource(_client(), "demo/repo", channels=["C1"])
    docs = list(src.fetch())
    # 3 raw messages, but the channel_join subtype is skipped -> 2 docs
    assert len(docs) == 2
    assert all(d.node_type == NodeType.MESSAGE for d in docs)


def test_slack_backfill_links_chat_to_issue():
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    store.upsert_node(Node(id=ids.issue_id("demo/repo", 12), type=NodeType.ISSUE, title="bug"))
    src = SlackBotSource(_client(), "demo/repo", channels=["C1"])
    ing.ingest_documents(src.fetch())
    edges = {(e.src, e.dst, e.type.value) for e in store.all_edges()}
    iss12 = ids.issue_id("demo/repo", 12)
    msg = ids.message_id("1700000000.000100")
    assert (iss12, msg, "discussed-in") in edges


def test_slack_live_event_to_document():
    src = SlackBotSource(_client(), "demo/repo", channels=["C1"])
    doc = src.event_to_document(
        {"type": "message", "channel": "C1", "ts": "1700000009.000999", "user": "ada", "text": "shipping #42"}
    )
    assert doc is not None
    assert doc.node_id == ids.message_id("1700000009.000999")
    # subtype events (edits/joins) are ignored
    assert src.event_to_document({"type": "message", "subtype": "message_changed"}) is None
