"""Shared worker result-doc parsing.

Extracts agent-agnostic parsing logic: payload integrity check, JSON doc parsing,
and Result mapping. Used by agent adapters to transform raw worker output into a
Result. Stdlib-only.
"""
from __future__ import annotations

import json
import time

from engine import contracts
from engine.models import Result

# Cap the captured failure detail so a runaway worker can't bloat the db.
_DETAIL_LIMIT = 16384


def parse_result_doc(raw: str, envelope: dict) -> Result:
    """Parse worker output into a Result.

    Integrity check first: recompute payload_sha256 over the received payload and,
    on mismatch, return driver_failed / contract_fail (no retry). Otherwise parse
    raw as the result JSON doc; an empty or unparseable doc is a driver_failed /
    driver_error.

    Args:
        raw: Worker's stdout (JSON result doc)
        envelope: The dispatch envelope (for payload integrity check)

    Returns:
        Result with outcome, termination_reason, payload, timestamps, refs, detail
    """
    now = time.time()

    expected = envelope.get("payload_sha256")
    actual = contracts.payload_sha256(envelope.get("payload") or {})
    if expected is not None and expected != actual:
        return _failure(
            "contract_fail",
            f"payload_sha256 mismatch: expected {expected}, got {actual}",
            now,
        )

    doc = _load_doc(raw)
    if doc is None:
        # Keep the raw output so the operator can see WHAT could not be parsed.
        return _failure(
            "driver_error", "empty or unparseable worker output", now,
            detail=(raw or "")[:_DETAIL_LIMIT] or None,
        )

    outcome = doc.get("outcome", "ok")
    termination_reason = doc.get(
        "termination_reason", "goal_met" if outcome == "ok" else "driver_error"
    )
    payload = doc.get("payload", {}) if outcome == "ok" else {}
    # A worker may report a stack trace / long detail alongside the summary.
    detail = doc.get("detail") or doc.get("stack_trace")
    return Result(
        outcome=outcome,
        termination_reason=termination_reason,
        result_ref=doc.get("result_ref"),
        error_summary=doc.get("error_summary"),
        started_at=doc.get("started_at", now),
        ended_at=doc.get("ended_at", now),
        payload=payload or {},
        evidence_ref=doc.get("evidence_ref"),
        detail=(str(detail)[:_DETAIL_LIMIT] if detail else None),
    )


def _load_doc(raw: str):
    """Parse raw into a result dict, or None if empty/unparseable."""
    if not raw or not raw.strip():
        return None
    try:
        doc = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return doc if isinstance(doc, dict) else None


def _failure(
    termination_reason: str, summary: str, now: float, detail: str | None = None
) -> Result:
    return Result(
        outcome="driver_failed",
        termination_reason=termination_reason,
        result_ref=None,
        error_summary=summary,
        started_at=now,
        ended_at=now,
        payload={},
        evidence_ref=None,
        detail=detail,
    )
