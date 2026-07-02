from datetime import datetime, timezone

from repomind import ids
from repomind.models import Message, NodeType
from repomind.sources.chat import message_from_dict, message_to_document


def test_message_to_document_builds_refs():
    msg = Message(
        message_id="100",
        author="ada",
        channel="dev",
        text="the login bug is #12, related to #7",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    doc = message_to_document(msg, "demo/repo")
    assert doc.node_id == ids.message_id("100")
    assert doc.node_type == NodeType.MESSAGE
    discussed = {(r.kind.value, r.value) for r in doc.references if r.edge.value == "discussed-in"}
    assert discussed == {("issue_number", "12"), ("issue_number", "7")}
    assert any(r.edge.value == "authored" for r in doc.references)


def test_message_from_dict_variants():
    m1 = message_from_dict({"id": "5", "content": "hi #3", "author": "grace", "channel": "g"})
    assert m1.message_id == "5"
    assert m1.text == "hi #3"
    assert m1.links == []

    m2 = message_from_dict(
        {
            "message_id": "6",
            "text": "see https://x.y/z",
            "author": "ada",
            "timestamp": "2026-01-01T00:00:00Z",
        }
    )
    assert m2.message_id == "6"
    assert m2.links == ["https://x.y/z"]
    assert m2.timestamp is not None


def test_message_from_dict_long_text_preview():
    long = "x" * 200
    doc = message_to_document(message_from_dict({"id": "9", "content": long, "author": "a"}), "r")
    assert doc.title.endswith("...")
