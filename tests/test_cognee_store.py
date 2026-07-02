"""Exercise CogneeMemoryStore's real logic by injecting a fake `cognee` module.

This verifies the adapter's structure delegation and the remember/improve/forget
lifecycle wiring without any network or real Cognee install.
"""
from __future__ import annotations

import sys
import types

import pytest

from repomind.models import Edge, EdgeType, Node, NodeType


class _FakeConfig:
    def __init__(self):
        self.api_key = None

    def set_llm_api_key(self, key):
        self.api_key = key


def make_fake_cognee():
    mod = types.ModuleType("cognee")
    calls = {"add": [], "cognify": 0, "search": [], "memify": 0, "delete": [], "prune": 0}
    mod._calls = calls
    mod.config = _FakeConfig()

    async def add(text, dataset_name=None):
        calls["add"].append((text, dataset_name))

    async def cognify(datasets=None):
        calls["cognify"] += 1

    async def search(query_text=None, **kwargs):
        calls["search"].append(query_text)
        return ["... result mentioning Fix login ..."]

    async def memify(datasets=None):
        calls["memify"] += 1

    async def delete(target, dataset_name=None):
        calls["delete"].append((target, dataset_name))

    prune_mod = types.SimpleNamespace()

    async def prune_data(dataset_name=None):
        calls["prune"] += 1

    prune_mod.prune_data = prune_data

    mod.add = add
    mod.cognify = cognify
    mod.search = search
    mod.memify = memify
    mod.delete = delete
    mod.prune = prune_mod
    return mod


@pytest.fixture
def fake_cognee(monkeypatch):
    mod = make_fake_cognee()
    monkeypatch.setitem(sys.modules, "cognee", mod)
    return mod


def _store(fake_cognee):
    from repomind.config import MemoryConfig
    from repomind.graph.cognee_store import CogneeMemoryStore

    return CogneeMemoryStore(MemoryConfig(backend="cognee", dataset="repomind"), api_key="test-key")


def test_init_sets_api_key(fake_cognee):
    _store(fake_cognee)
    assert fake_cognee.config.api_key == "test-key"


def test_upsert_buffers_and_remember_flush(fake_cognee):
    store = _store(fake_cognee)
    store.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    store.upsert_node(Node(id="p:ada", type=NodeType.PERSON, title="ada"))
    store.upsert_edge(Edge(src="p:ada", dst="pr:1", type=EdgeType.AUTHORED))
    assert store.get_node("pr:1").title == "Fix login"
    assert store.counts()["edges"] == 1
    store.remember_flush()
    # One combined add (not one per node) + one cognify.
    assert len(fake_cognee._calls["add"]) == 1
    assert "Fix login" in fake_cognee._calls["add"][0][0]
    assert fake_cognee._calls["cognify"] == 1


def test_search_maps_recall_back_to_nodes(fake_cognee):
    store = _store(fake_cognee)
    store.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    hits = store.search("login")
    assert fake_cognee._calls["search"] == ["login"]
    assert any(n.id == "pr:1" for n in hits)


def test_improve_calls_memify(fake_cognee):
    store = _store(fake_cognee)
    store.improve()
    assert fake_cognee._calls["memify"] == 1


def test_forget_with_target_calls_delete(fake_cognee):
    store = _store(fake_cognee)
    store.forget("pr:1")
    assert fake_cognee._calls["delete"] == [("pr:1", "repomind")]


def test_hard_delete_triggers_forget(fake_cognee):
    store = _store(fake_cognee)
    store.upsert_node(Node(id="pr:1", type=NodeType.PULL_REQUEST, title="Fix login"))
    assert store.hard_delete("pr:1") is True
    assert store.get_node("pr:1") is None
    assert fake_cognee._calls["delete"] == [("pr:1", "repomind")]


def test_tombstone_delegates(fake_cognee):
    store = _store(fake_cognee)
    store.upsert_node(Node(id="f:1", type=NodeType.FILE, title="auth.py"))
    store.tombstone_node("f:1", deleted_in="abc")
    assert store.get_node("f:1").status == "deleted"
