import hashlib
import hmac

from repomind import ids
from repomind.graph.store import InMemoryGraphStore
from repomind.models import NodeType
from repomind.pipeline.ingest import Ingestor
from repomind.webhook import event_to_documents, verify_signature


def test_verify_signature():
    secret = "s3cret"
    body = b'{"hello":"world"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(secret, body, sig)
    assert not verify_signature(secret, body, "sha256=deadbeef")
    assert not verify_signature(secret, body, None)


def test_pull_request_event_to_documents():
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Add retry logic",
            "body": "Fixes #7. cc @grace",
            "user": {"login": "ada"},
            "state": "open",
            "merged": False,
        },
        "repository": {"full_name": "demo/repo"},
    }
    docs = event_to_documents("pull_request", payload, "demo/repo")
    assert len(docs) == 1
    d = docs[0]
    assert d.node_id == ids.pr_id("demo/repo", 42)
    kinds = {(r.kind.value, r.value) for r in d.references}
    assert ("closes_issue", "7") in kinds
    assert ("person_login", "ada") in kinds
    assert ("person_login", "grace") in kinds


def test_issue_deleted_action_marks_deleted():
    payload = {
        "action": "deleted",
        "issue": {"number": 7, "title": "bug", "body": "", "user": {"login": "grace"}, "state": "open"},
        "repository": {"full_name": "demo/repo"},
    }
    docs = event_to_documents("issues", payload, "demo/repo")
    assert docs[0].deleted is True


def test_push_event_tombstones_removed_files():
    payload = {
        "commits": [
            {
                "id": "deadbeef",
                "message": "remove legacy auth, closes #9",
                "author": {"username": "ada"},
                "added": ["new.py"],
                "modified": ["db.py"],
                "removed": ["legacy_auth.py"],
            }
        ],
        "repository": {"full_name": "demo/repo"},
    }
    docs = event_to_documents("push", payload, "demo/repo")
    commit_docs = [d for d in docs if d.node_type == NodeType.COMMIT]
    file_dels = [d for d in docs if d.node_type == NodeType.FILE and d.deleted]
    assert len(commit_docs) == 1
    assert file_dels and file_dels[0].title == "legacy_auth.py"
    assert file_dels[0].attributes["deleted_in"] == "deadbeef"


def test_webhook_docs_flow_through_ingest():
    store = InMemoryGraphStore()
    ing = Ingestor(store)
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Add retry logic",
            "body": "Fixes #7",
            "user": {"login": "ada"},
            "state": "open",
        },
        "repository": {"full_name": "demo/repo"},
    }
    docs = event_to_documents("pull_request", payload, "demo/repo")
    ing.ingest_documents(docs)
    assert store.has_node(ids.pr_id("demo/repo", 42))
    assert store.has_node(ids.person_id("ada"))
