"""RepoMind engine: the orchestration facade used by both the API and the CLI.

Wires the configured GraphStore, the ingest engine, operational state, and the
query engine, and exposes the high-level operations: backfill, ingest Discord,
handle a webhook, manual sync (incremental/full with reconcile), verify, and
improve. Every path funnels Documents through the single Ingestor.
"""
from __future__ import annotations

from repomind.config import Config
from repomind.graph.store import GraphStore, InMemoryGraphStore
from repomind.models import Document, Message, NodeType
from repomind.pipeline.ingest import Ingestor
from repomind.query import QueryEngine
from repomind.sources.discord_source import DiscordExportSource
from repomind.sources.git_source import GitSource
from repomind.state import StateStore

# Node types each source is authoritative for (used by full-sync reconcile).
_GIT_TYPES = {NodeType.COMMIT}
_GITHUB_PR_TYPES = {NodeType.PULL_REQUEST}
_GITHUB_ISSUE_TYPES = {NodeType.ISSUE}


def build_store(config: Config) -> GraphStore:
    if config.memory.backend == "cognee_cloud":
        from repomind.graph.cognee_cloud_store import CogneeCloudStore

        return CogneeCloudStore(
            config.memory,
            config.cognee_api_key(),
            config.cognee_service_url(),
        )
    if config.memory.backend == "cognee":
        from repomind.graph.cognee_store import CogneeMemoryStore

        return CogneeMemoryStore(config.memory, config.cognee_api_key())
    store = InMemoryGraphStore()
    if config.memory.persist_path:
        store.load(config.memory.persist_path)
    return store


class Engine:
    def __init__(self, config: Config, store: GraphStore | None = None) -> None:
        self.config = config
        self.store = store or build_store(config)
        self.ingestor = Ingestor(self.store)
        self.state = StateStore(config.state.db_path)
        self.query_engine = QueryEngine(self.store)
        # An injectable factory for the GitHub source so tests can supply a fake.
        self._github_source_factory = None

    # -- wiring helpers ------------------------------------------------------
    def set_github_source(self, source) -> None:
        """Inject a GitHubSource (or compatible) instance, e.g. for tests."""
        self._github_source_factory = lambda: source

    def _make_github_source(self):
        if self._github_source_factory is not None:
            return self._github_source_factory()
        token = self.config.github_token()
        if not token or not self.config.repo.name:
            return None
        from repomind.sources.github_source import GitHubSource

        return GitHubSource.from_token(token, self.config.repo.name)

    # -- ingestion -----------------------------------------------------------
    def backfill_git(self, since: str | None = None) -> int:
        if not self.config.repo.local_path:
            return 0
        src = GitSource(
            self.config.repo.local_path,
            self.config.repo.name or "local",
            max_commits=self.config.ingest.max_commits or None,
        )
        return self.ingestor.ingest_documents(src.fetch(since))

    def backfill_github(self) -> int:
        src = self._make_github_source()
        if src is None:
            return 0
        return self.ingestor.ingest_documents(src.fetch())

    def ingest_discord(self, export_path: str) -> int:
        src = DiscordExportSource(export_path, self.config.repo.name or "local")
        return self.ingestor.ingest_documents(src.fetch())

    def ingest_documents(self, docs: list[Document]) -> int:
        return self.ingestor.ingest_documents(docs)

    def ingest_source(self, source) -> int:
        """Generic Phase 2 path: ingest any Source (Slack/Discord bot, etc.)."""
        return self.ingestor.ingest_documents(source.fetch())

    # -- live chat events + n8n low-code path (Phase 2) ---------------------
    def ingest_chat_message(self, message: Message) -> int:
        """Ingest a single normalized chat Message (live Slack/Discord event)."""
        from repomind.sources.chat import message_to_document

        doc = message_to_document(message, self.config.repo.name or "local")
        return self.ingestor.ingest_documents([doc])

    def ingest_chat_dict(self, data: dict) -> dict:
        """Ingest a loose chat-message dict (the n8n / Option C low-code path)."""
        from repomind.sources.chat import message_from_dict

        msg = message_from_dict(data)
        if not msg.message_id:
            return {"status": "error", "reason": "missing message id", "ingested": 0}
        n = self.ingest_chat_message(msg)
        return {"status": "ok", "ingested": n, "node_id": f"discord:msg:{msg.message_id}"}

    # -- webhook -------------------------------------------------------------
    def handle_webhook(self, event_type: str, payload: dict, delivery_id: str | None) -> dict:
        from repomind.webhook import event_to_documents

        if delivery_id and self.state.is_processed(delivery_id):
            return {"status": "duplicate", "delivery_id": delivery_id, "ingested": 0}
        docs = event_to_documents(event_type, payload, self.config.repo.name)
        n = self.ingestor.ingest_documents(docs)
        if delivery_id:
            self.state.mark_processed(delivery_id)
        return {"status": "ok", "delivery_id": delivery_id, "ingested": n}

    # -- manual sync + reconcile --------------------------------------------
    def sync(self, scope: str = "all", mode: str = "incremental") -> dict:
        """Force a re-sync. Full mode reconciles: anything missing upstream is
        tombstoned, drift is corrected via idempotent upserts."""
        report: dict = {"scope": scope, "mode": mode, "ingested": 0, "tombstoned": 0}
        emitted_ids: dict[NodeType, set[str]] = {}

        def run(src, track_types: set[NodeType] | None):
            if src is None:
                return
            docs = list(src.fetch())
            report["ingested"] += self.ingestor.ingest_documents(docs)
            if track_types:
                for d in docs:
                    if d.node_type in track_types:
                        emitted_ids.setdefault(d.node_type, set()).add(d.node_id)

        if scope in ("all", "commits") and self.config.repo.local_path:
            run(
                GitSource(
                    self.config.repo.local_path,
                    self.config.repo.name or "local",
                    max_commits=self.config.ingest.max_commits or None,
                ),
                _GIT_TYPES,
            )
        if scope in ("all", "prs", "issues"):
            run(self._make_github_source(), _GITHUB_PR_TYPES | _GITHUB_ISSUE_TYPES)

        # Reconcile only on a full sync, and only for types we fully re-read.
        if mode == "full":
            report["tombstoned"] = self._reconcile(scope, emitted_ids)

        self.improve()
        report["unresolved"] = self.ingestor.unresolved_count
        return report

    def _reconcile(self, scope: str, emitted_ids: dict[NodeType, set[str]]) -> int:
        type_filter: set[NodeType] = set()
        if scope in ("all", "commits"):
            type_filter |= _GIT_TYPES
        if scope in ("all", "prs"):
            type_filter |= _GITHUB_PR_TYPES
        if scope in ("all", "issues"):
            type_filter |= _GITHUB_ISSUE_TYPES

        tombstoned = 0
        for node in self.store.all_nodes(include_deleted=False):
            if node.type not in type_filter:
                continue
            seen = emitted_ids.get(node.type, set())
            if node.id not in seen:
                # Present in graph, absent upstream -> it vanished; tombstone it.
                if self.store.tombstone_node(node.id, deleted_in="reconcile"):
                    tombstoned += 1
        return tombstoned

    # -- verification --------------------------------------------------------
    def verify(self, scope: str = "all") -> dict:
        """Re-read sources and diff against the graph; returns a discrepancy
        report. A full sync is the repair action; verify is read-mostly but will
        add anything missing through the idempotent pipeline."""
        before = self.store.counts()
        report = self.sync(scope=scope, mode="full")
        after = self.store.counts()
        return {
            "scope": scope,
            "added_or_updated": report["ingested"],
            "tombstoned": report["tombstoned"],
            "unresolved_references": self.ingestor.unresolved_report(),
            "counts_before": before,
            "counts_after": after,
            "consistent": self.ingestor.unresolved_count == 0,
        }

    # -- lifecycle -----------------------------------------------------------
    def improve(self) -> None:
        # Flush buffered texts into Cognee (real backend), then enrich.
        flush = getattr(self.store, "remember_flush", None)
        if callable(flush):
            flush()
        improve = getattr(self.store, "improve", None)
        if callable(improve):
            improve()
        # Persist the structural graph for any backend that supports it
        # (in-memory and the Cognee adapter both expose save()).
        saver = getattr(self.store, "save", None)
        if self.config.memory.persist_path and callable(saver):
            saver(self.config.memory.persist_path)

    def forget(self, target: str) -> bool:
        """True hard erase (privacy/secret/junk). Hard delete + Cognee forget."""
        return self.store.hard_delete(target)

    # -- query ---------------------------------------------------------------
    def query(self, question: str, limit: int = 5) -> dict:
        return self.query_engine.answer(question, limit=limit)

    def counts(self) -> dict:
        return self.store.counts()

    def close(self) -> None:
        self.state.close()
