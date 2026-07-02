"""Exercise CogneeCloudStore against a fake CloudClient (no network, no key).

Verifies structure delegation and the add/cognify/search/memify wiring, plus
graceful degradation to local search when the cloud returns nothing.
"""
from __future__ import annotations

from repomind.config import MemoryConfig
from repomind.graph.cognee_cloud_store import CogneeCloudStore
from repomind.models import Edge, EdgeType, Node, NodeType


class FakeCloudClient:
    def __init__(self, search_result=None):
        self.calls = {"add": [], "cognify": [], "search": [], "memify": []}
        self._search_result = search_result if search_result is not None else []

    def add(self, text, dataset):
        self.calls["add"].append((text, dataset))
        return {"ok": True}

    def cognify(self, dataset):
        self.calls["cognify"].append(dataset)
        return {"ok": True}

    def search(self, query, search_type, dataset, top_k):
        self.calls["search"].append((query, search_type, dataset, top_k))
        return self._search_result

    def memify(self, dataset):
        self.calls["memify"].append(dataset)
        return {"ok": True}


def _store(client):
    return CogneeCloudStore(
        MemoryConfig(backend="cognee_cloud", dataset="repomind"),
        api_key="ck_test",
        service_url="https://example.test",
        client=client,
    )


def test_missing_key_or_url_raises():
    import pytest

    with pytest.raises(ValueError):
        CogneeCloudStore(MemoryConfig(backend="cognee_cloud"), api_key=None, service_url=None)


def test_upsert_buffers_then_flush_adds_and_cognifies():
    client = FakeCloudClient()
    store = _store(client)
    store.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    store.upsert_node(Node(id="p:ada", type=NodeType.PERSON, title="ada"))
    store.upsert_edge(Edge(src="p:ada", dst="pr:1", type=EdgeType.AUTHORED))
    assert store.counts()["edges"] == 1
    store.remember_flush()
    # One combined add (not one per node) + one cognify, both on our dataset.
    assert len(client.calls["add"]) == 1
    assert "Fix login" in client.calls["add"][0][0]
    assert client.calls["add"][0][1] == "repomind"
    assert client.calls["cognify"] == ["repomind"]


def test_search_maps_cloud_hits_back_to_nodes():
    client = FakeCloudClient(search_result=["... chunk mentioning Fix login ..."])
    store = _store(client)
    store.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    hits = store.search("login")
    assert client.calls["search"][0][0] == "login"
    assert any(n.id == "pr:1" for n in hits)


def test_search_falls_back_to_local_when_cloud_empty():
    client = FakeCloudClient(search_result=[])
    store = _store(client)
    store.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    hits = store.search("login")
    # No cloud hits -> deterministic local keyword search still finds it.
    assert any(n.id == "pr:1" for n in hits)


def test_search_degrades_when_cloud_raises():
    class Boom(FakeCloudClient):
        def search(self, *a, **k):
            raise RuntimeError("cloud down")

    store = _store(Boom())
    store.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    hits = store.search("login")
    assert any(n.id == "pr:1" for n in hits)


def test_improve_calls_memify():
    client = FakeCloudClient()
    store = _store(client)
    store.improve()
    assert client.calls["memify"] == ["repomind"]


def test_flush_survives_cloud_failure():
    class Boom(FakeCloudClient):
        def add(self, *a, **k):
            raise RuntimeError("cloud down")

    store = _store(Boom())
    store.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    store.remember_flush()  # must not raise; structure remains intact
    assert store.get_node("pr:1").title == "Fix login"


def test_structure_methods_delegate():
    store = _store(FakeCloudClient())
    store.upsert_node(Node(id="f:1", type=NodeType.FILE, title="auth.py"))
    store.tombstone_node("f:1", deleted_in="abc")
    assert store.get_node("f:1").status == "deleted"
    assert store.hard_delete("f:1") is True
    assert store.get_node("f:1") is None
