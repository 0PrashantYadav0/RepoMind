"""Core domain models: Documents (source output), Nodes, Edges, References.

A Source emits Documents. The ingest pipeline turns Documents into graph
Nodes + Edges (resolving References into edges against stable IDs).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    FILE = "File"
    COMMIT = "Commit"
    PULL_REQUEST = "PullRequest"
    ISSUE = "Issue"
    PERSON = "Person"
    DECISION = "Decision"
    MESSAGE = "Message"
    MODULE = "Module"


class EdgeType(str, Enum):
    AUTHORED = "authored"          # Person -> Commit/PR/Issue/Message
    REVIEWED = "reviewed"          # Person -> PullRequest
    CLOSES = "closes"              # PR/Commit -> Issue
    MENTIONS = "mentions"          # any -> any (textual reference)
    MODIFIES = "modifies"          # Commit -> File
    PART_OF = "part-of"            # File -> Module
    DEPENDS_ON = "depends-on"      # File -> File
    DISCUSSED_IN = "discussed-in"  # PR/Issue/Decision -> Message
    DECIDED_IN = "decided-in"      # Decision -> PR/Issue
    COMMENTED_ON = "commented-on"  # Message/Person -> PR/Issue


class RefKind(str, Enum):
    """A typed, unresolved pointer found in source text/metadata.

    The resolver turns these into concrete edges once the target ID is known.
    """
    ISSUE_NUMBER = "issue_number"   # "#455"
    PR_NUMBER = "pr_number"         # "#482"
    PERSON_LOGIN = "person_login"   # "@octocat"
    FILE_PATH = "file_path"         # "src/auth.py"
    CLOSES_ISSUE = "closes_issue"   # "Fixes #455" / "Closes #12"


class Reference(BaseModel):
    """An unresolved link from this document to some other entity."""
    kind: RefKind
    value: str
    # Optional explicit edge type override; if None the resolver picks a default.
    edge: EdgeType | None = None


class Document(BaseModel):
    """Normalized unit emitted by every Source. One Document -> one primary node.

    `node_id` is the stable ID (see ids.py). `node_type` says what it becomes.
    `references` are resolved into edges by the pipeline.
    """
    node_id: str
    node_type: NodeType
    title: str = ""
    body: str = ""
    repo: str = ""
    author_login: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Arbitrary typed attributes stored on the node (state, sha, number, etc.).
    attributes: dict = Field(default_factory=dict)
    references: list[Reference] = Field(default_factory=list)
    # True when the source reports this entity as deleted upstream.
    deleted: bool = False


class Message(BaseModel):
    """Normalized chat message (Discord export or, in Phase 2, live bots)."""
    message_id: str
    author: str
    timestamp: datetime | None = None
    channel: str = ""
    thread_id: str | None = None
    text: str = ""
    links: list[str] = Field(default_factory=list)


class Node(BaseModel):
    """A vertex in the knowledge graph."""
    id: str
    type: NodeType
    title: str = ""
    body: str = ""
    attributes: dict = Field(default_factory=dict)
    status: str = "active"            # "active" | "deleted" (tombstone)
    deleted_in: str | None = None     # commit sha / PR id that removed it
    schema_version: int = 1

    def text_for_embedding(self) -> str:
        return f"{self.type.value}: {self.title}\n{self.body}".strip()


class Edge(BaseModel):
    """A directed, typed relationship between two nodes."""
    src: str
    dst: str
    type: EdgeType
    attributes: dict = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.src, self.dst, self.type.value)


class UnresolvedRef(BaseModel):
    """A reference that could not be resolved yet (target not ingested).

    Parked and retried after later ingests so edges are never created against
    a guessed or wrong target.
    """
    src: str
    ref: Reference
    repo: str
