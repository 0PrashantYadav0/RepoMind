"""Source connector interface. Every source emits normalized Documents.

The contract is intentionally tiny (Interface Segregation): a source knows how
to `fetch` Documents, optionally since a cursor. Backfill and incremental both
go through the same method, so there is one code path (correctness).
"""
from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from repomind.models import Document


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch(self, since: str | None = None) -> Iterable[Document]:
        """Yield Documents. `since` is a source-specific cursor (sha/timestamp).
        When None, performs a full backfill."""
        ...
