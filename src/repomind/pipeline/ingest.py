"""The ingest engine: the ONE idempotent code path that every trigger (backfill,
webhook, poller, manual sync) funnels through.

For each Document it:
  1. upserts the primary node (idempotent by stable ID), or tombstones it if the
     source reports it deleted (history-preserving);
  2. resolves references into edges, creating identity-bearing target nodes on
     demand and parking numeric refs whose target is not present yet;
  3. retries parked references after each ingest, so edges appear as soon as
     their target arrives -- never against a guessed target.
"""
from __future__ import annotations

from repomind.graph.store import GraphStore
from repomind.models import Document, Node, UnresolvedRef
from repomind.pipeline.resolver import resolve_reference


class Ingestor:
    def __init__(self, store: GraphStore) -> None:
        self.store = store
        self._unresolved: list[UnresolvedRef] = []

    @property
    def unresolved_count(self) -> int:
        return len(self._unresolved)

    def _node_from_document(self, doc: Document) -> Node:
        return Node(
            id=doc.node_id,
            type=doc.node_type,
            title=doc.title,
            body=doc.body,
            attributes=dict(doc.attributes),
            status="active",
        )

    def ingest_document(self, doc: Document) -> None:
        if doc.deleted:
            # History-preserving deletion (tombstone). Create-then-tombstone if
            # we never saw it, so the fact "it existed and was removed" survives.
            if not self.store.has_node(doc.node_id):
                self.store.upsert_node(self._node_from_document(doc))
            deleted_in = doc.attributes.get("deleted_in")
            self.store.tombstone_node(doc.node_id, deleted_in=deleted_in)
            return

        # Upsert the primary node (idempotent).
        self.store.upsert_node(self._node_from_document(doc))

        # Resolve this document's references into edges.
        for ref in doc.references:
            result = resolve_reference(doc.node_id, ref, doc.repo, self.store)
            if result.new_node is not None:
                self.store.upsert_node(result.new_node)
            if result.edge is not None:
                self.store.upsert_edge(result.edge)
            if result.unresolved is not None:
                self._unresolved.append(result.unresolved)

        # A newly added node may unblock previously parked references.
        self.retry_unresolved()

    def ingest_documents(self, docs) -> int:
        n = 0
        for doc in docs:
            self.ingest_document(doc)
            n += 1
        # Final sweep in case ordering left anything parked.
        self.retry_unresolved()
        return n

    def retry_unresolved(self) -> int:
        if not self._unresolved:
            return 0
        still: list[UnresolvedRef] = []
        resolved = 0
        for item in self._unresolved:
            result = resolve_reference(item.src, item.ref, item.repo, self.store)
            if result.edge is not None:
                if result.new_node is not None:
                    self.store.upsert_node(result.new_node)
                self.store.upsert_edge(result.edge)
                resolved += 1
            else:
                still.append(item)
        self._unresolved = still
        return resolved

    def unresolved_report(self) -> list[dict]:
        return [
            {"src": u.src, "kind": u.ref.kind.value, "value": u.ref.value, "repo": u.repo}
            for u in self._unresolved
        ]
