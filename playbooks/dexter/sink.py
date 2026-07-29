"""LearningSink protocol + implementations for dexter playbook (Slice 4).

The LearningSink interface defines bank(cluster) -> str|None. Implementations:
- FakeSink: test double that records calls and returns a canned ref (or raises)
- DexterKbSink: shells to dexter plugin kb.py (validate + index)

Stdlib-only.
"""
from __future__ import annotations

import subprocess
from typing import Protocol


class LearningSink(Protocol):
    """Protocol for banking a learning from a cluster (§5)."""

    def bank(self, cluster: dict) -> str | None:
        """Bank a learning for a cluster.

        Args:
            cluster: Dict containing cluster data (signature, canonical_ticket_id, etc.)

        Returns:
            Learning ref (e.g. "kb/2026-07-29-npe-config.md") on success, None on failure.

        Raises:
            Exception: May raise on unrecoverable failure (caller must catch).
        """
        ...


class FakeSink:
    """Test-double sink that records calls and returns a canned ref (or raises)."""

    def __init__(self, ref: str | None = None, raise_on_bank: Exception | None = None):
        """Initialize FakeSink.

        Args:
            ref: Canned learning ref to return from bank() (default None).
            raise_on_bank: If set, bank() raises this exception after recording the call.
        """
        self.ref = ref
        self.raise_on_bank = raise_on_bank
        self.banked_clusters: list[dict] = []

    def bank(self, cluster: dict) -> str | None:
        """Record the cluster and return the canned ref (or raise if configured)."""
        self.banked_clusters.append(cluster)

        if self.raise_on_bank is not None:
            raise self.raise_on_bank

        return self.ref


class DexterKbSink:
    """Production sink: shells to dexter plugin kb.py (validate + index).

    Expects:
    - INVESTIGATIONS_DIR env var pointing to the dexter runtime dir
    - dexter plugin installed (kb.py on PATH or via ${CLAUDE_PLUGIN_ROOT}/dexter/scripts/kb.py)

    This is the single master-side dexter coupling (§5).
    """

    def bank(self, cluster: dict) -> str | None:
        """Bank a learning via dexter kb.py validate + index.

        Args:
            cluster: Cluster dict with signature, canonical_ticket_id, etc.

        Returns:
            Learning ref on success, None on failure.

        Raises:
            subprocess.CalledProcessError: If kb.py fails (caller catches).
        """
        # For now, this is a stub that would shell to kb.py
        # Full implementation would:
        # 1. Generate a knowledge entry from the cluster
        # 2. Call kb.py validate <entry-file>
        # 3. Call kb.py index <entry-file>
        # 4. Return the ref
        #
        # Since reduce must never raise and we're in a best-effort context,
        # the caller will wrap this in try/except.
        raise NotImplementedError(
            "DexterKbSink.bank() is a stub; full implementation shells to kb.py"
        )
