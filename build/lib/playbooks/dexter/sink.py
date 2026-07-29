"""Learning sink protocol and implementations for banking dexter findings. Includes test double and production kb.py integration."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Protocol


class LearningSink(Protocol):
    """Protocol for banking a learning from a cluster."""

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
    - DEXTER_KB_PY env var pointing to kb.py script
    - INVESTIGATIONS_DIR env var pointing to the dexter runtime dir

    This is the single master-side dexter coupling.
    """

    def bank(self, cluster: dict) -> str | None:
        """Bank a learning via dexter kb.py validate + index.

        Args:
            cluster: Cluster dict with signature, canonical_ticket_id, etc.

        Returns:
            Learning ref (e.g. "kb/slug") on success, None on failure/not-configured.

        Best-effort: returns None if not configured or validation/indexing fails.
        Never raises (honest "not banked" via None return).
        """
        # Check configuration from env
        kb_py_path = os.environ.get("DEXTER_KB_PY", "").strip()
        investigations_dir = os.environ.get("INVESTIGATIONS_DIR", "").strip()

        if not kb_py_path or not investigations_dir:
            # Not configured → return None (honest "not banked")
            return None

        try:
            # Build a knowledge entry document from cluster
            slug = self._build_slug(cluster)
            entry_doc = self._build_knowledge_entry(cluster, slug)

            # Write to temp file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.md',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(entry_doc)
                entry_path = f.name

            try:
                # 1. Validate
                result = subprocess.run(
                    ["python3", kb_py_path, "validate", entry_path],
                    env={**os.environ, "INVESTIGATIONS_DIR": investigations_dir},
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    # Validation failed → return None
                    return None

                # 2. Index (validate passed)
                result = subprocess.run(
                    ["python3", kb_py_path, "index", entry_path],
                    env={**os.environ, "INVESTIGATIONS_DIR": investigations_dir},
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    # Index failed → return None
                    return None

                # Success: return a ref
                return f"kb/{slug}"

            finally:
                # Clean up temp file
                try:
                    os.unlink(entry_path)
                except Exception:
                    pass

        except Exception:
            # Best-effort: any error → return None
            return None

    def _build_slug(self, cluster: dict) -> str:
        """Build a slug for the knowledge entry from cluster signature."""
        sig = cluster.get("signature", "unknown")
        # Simple slug: lowercase, replace non-alphanum with hyphen
        import re
        slug = re.sub(r'[^a-z0-9]+', '-', sig.lower()).strip('-')
        return slug or "unknown"

    def _build_knowledge_entry(self, cluster: dict, slug: str) -> str:
        """Build a minimal knowledge entry document from cluster data.

        This is a minimal scaffold; real dexter kb.py validate will likely
        require more fields. For now, we include what we have from the cluster.
        """
        sig = cluster.get("signature", "Unknown")
        cause_category = cluster.get("cause_category", "unknown")
        canonical_ticket_id = cluster.get("canonical_ticket_id", "")
        canonical_diff_ref = cluster.get("canonical_diff_ref", "")
        member_ticket_ids = cluster.get("member_ticket_ids", [])

        # Build a minimal markdown doc
        # (Real implementation would need full frontmatter + all required sections)
        doc = f"""---
slug: {slug}
signature: {sig}
cause_category: {cause_category}
---

# {sig}

## Root Cause

Category: {cause_category}

## Evidence

Canonical ticket: {canonical_ticket_id}
Canonical diff: {canonical_diff_ref}
Member tickets: {', '.join(member_ticket_ids)}

## Fix

See diff: {canonical_diff_ref}

## Impact

TBD

## Mitigation

TBD

## Prevention

TBD

## Related

TBD
"""
        return doc
