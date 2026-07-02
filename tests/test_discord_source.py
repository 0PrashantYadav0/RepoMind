from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import Node, NodeType
from repomind.pipeline.ingest import Ingestor
from repomind.sources.discord_source import DiscordExportSource, parse_export


def test_parse_export(discord_export):
    channel, messages = parse_export(discord_export)
    assert channel == "dev"
    assert len(messages) == 2
    assert messages[0].author == "Ada"  # nickname preferred over name
    assert messages[1].links == ["https://example.com/spec"]


def test_discord_source_links_chat_to_issue(discord_export):
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    # Seed the issue so the discussed-in reference (#12) resolves.
    iss12 = ids.issue_id("demo/repo", 12)
    store.upsert_node(Node(id=iss12, type=NodeType.ISSUE, title="login bug"))

    src = DiscordExportSource(discord_export, "demo/repo")
    ing.ingest_documents(src.fetch())

    edges = {(e.src, e.dst, e.type.value) for e in store.all_edges()}
    msg_id = ids.message_id("100")
    # discussed-in is reversed: issue -> message
    assert (iss12, msg_id, "discussed-in") in edges
    # author edge exists too
    assert (ids.person_id("Ada"), msg_id, "authored") in edges
