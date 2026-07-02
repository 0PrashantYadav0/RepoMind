from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import Node, NodeType
from repomind.pipeline.ingest import Ingestor
from repomind.sources.discord_bot_source import DiscordBotSource
from tests.fakes import FakeDiscordAuthor, FakeDiscordChannel, FakeDiscordMessage


def _channels():
    msgs = [
        FakeDiscordMessage(id=100, author=FakeDiscordAuthor("ada", "Ada"), content="login bug is #12"),
        FakeDiscordMessage(id=101, author=FakeDiscordAuthor("grace"), content="on it"),
    ]
    return [FakeDiscordChannel("dev", msgs)]


def test_discord_bot_backfill():
    src = DiscordBotSource(_channels(), "demo/repo")
    docs = list(src.fetch())
    assert len(docs) == 2
    assert docs[0].author_login == "Ada"  # display_name preferred
    assert docs[0].node_id == ids.message_id("100")


def test_discord_bot_links_chat_to_issue():
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    store.upsert_node(Node(id=ids.issue_id("demo/repo", 12), type=NodeType.ISSUE, title="bug"))
    src = DiscordBotSource(_channels(), "demo/repo")
    ing.ingest_documents(src.fetch())
    edges = {(e.src, e.dst, e.type.value) for e in store.all_edges()}
    assert (ids.issue_id("demo/repo", 12), ids.message_id("100"), "discussed-in") in edges


def test_discord_bot_live_message():
    src = DiscordBotSource(_channels(), "demo/repo")
    live = FakeDiscordMessage(id=999, author=FakeDiscordAuthor("ada"), content="shipping #42")
    doc = src.message_to_document(live, "dev")
    assert doc.node_id == ids.message_id("999")
    assert doc.node_type == NodeType.MESSAGE
