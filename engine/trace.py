"""Capture a worker's own trace at the moment its result is recorded.

A ``result_ref`` such as ``claude:session:<uuid>`` names a transcript that lives
on the worker's host, in that agent tool's private state directory. Nothing but
the ref reaches the master, so the trace behind it was previously reachable only
by someone with a shell on the right box -- and only until the agent tool pruned
it. The control plane, which runs containerized with just ``HERMES_HOME``
mounted, could never read it at all.

So the trace is pulled across at result time instead of chased later: while the
host is still up, the file still exists, and the site still has a transport to
it. It lands under ``HERMES_HOME/runs/<run_id>/traces/<attempt_id>.jsonl``, which
the server can already read, and which stays put when the agent tool cleans up
after itself.

The engine asks two optional questions and knows nothing else:

  * ``agent.trace_source(result, envelope) -> str | None`` -- a host-side path or
    glob. Only the agent knows what its own refs mean.
  * ``site.fetch_file(host, source, dest) -> bool`` -- copy that path back. Only
    the site knows how to reach the host.

An adapter that implements neither simply captures nothing. **No failure here is
ever allowed to reach the dispatch**: a trace is evidence about a result, not
part of producing one, and losing it must never turn a good run bad.

Stdlib-only.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from engine import config, log
from engine.models import Result

# Traces are whole agent sessions and run to hundreds of KB routinely; a runaway
# one should not quietly fill the home. Past this, the trace is dropped rather
# than half-kept -- a truncated transcript reads as a complete one.
DEFAULT_MAX_MB = 50

# run_id and attempt_id both arrive from callers that took them off a URL path.
# They compose a filesystem path, so they are validated, not sanitized: anything
# that is not the shape we mint ourselves is refused outright.
_RUN_ID_OK = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def max_bytes() -> int:
    """The largest trace worth keeping, from ``HERMES_TRACE_MAX_MB``."""
    raw = os.environ.get("HERMES_TRACE_MAX_MB")
    try:
        mb = int(raw) if raw else DEFAULT_MAX_MB
    except (TypeError, ValueError):
        mb = DEFAULT_MAX_MB
    if mb <= 0:
        mb = DEFAULT_MAX_MB
    return mb * 1024 * 1024


def trace_path(run_id: str, attempt_id) -> Path:
    """Where the trace for one attempt lives.

    Raises:
        ValueError: if ``run_id`` or ``attempt_id`` is not the shape the engine
            mints -- these compose a path, and a caller that took them from a
            URL must not be able to walk out of the runs directory.
    """
    if not isinstance(run_id, str) or not _RUN_ID_OK.match(run_id):
        raise ValueError(f"unusable run_id for a trace path: {run_id!r}")
    try:
        attempt = int(attempt_id)
    except (TypeError, ValueError):
        raise ValueError(f"unusable attempt_id for a trace path: {attempt_id!r}") from None
    if attempt < 0:
        raise ValueError(f"unusable attempt_id for a trace path: {attempt_id!r}")
    return config.resolve_home() / "runs" / run_id / "traces" / f"{attempt}.jsonl"


def size(run_id: str, attempt_id) -> Optional[int]:
    """Bytes of captured trace for one attempt, or None if there is none."""
    try:
        path = trace_path(run_id, attempt_id)
        return path.stat().st_size
    except (ValueError, OSError):
        return None


def read(run_id: str, attempt_id) -> Optional[str]:
    """The captured trace for one attempt, or None if there is none.

    Undecodable bytes are replaced rather than raised: a trace that is partly
    unreadable is still worth showing.
    """
    try:
        path = trace_path(run_id, attempt_id)
        return path.read_text(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        return None


def capture(*, site, host: str, agent, result, envelope: dict,
            run_id: str, attempt_id) -> Optional[Path]:
    """Pull this attempt's trace back from the host. Best-effort, never raises.

    Returns the path written, or None when there was nothing to capture, no way
    to capture it, or the capture failed. Every one of those is normal.
    """
    logger = log.get_logger("trace")

    source = _ask_agent(agent, result, envelope, logger)
    if not source:
        return None

    fetch = getattr(site, "fetch_file", None)
    if not callable(fetch):
        logger.debug(f"site cannot fetch files; no trace for attempt {attempt_id}")
        return None

    try:
        dest = trace_path(run_id, attempt_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.parent.chmod(0o700)
    except (ValueError, OSError) as exc:
        logger.warning(f"no place to put the trace for attempt {attempt_id}: {exc}")
        return None

    # A stale trace from an earlier capture of the same attempt must not survive
    # a fetch that fails -- it would read as this attempt's.
    _discard(dest)

    try:
        ok = fetch(host, source, dest)
    except Exception as exc:  # transport of any kind, from any site
        logger.warning(f"could not fetch the trace for attempt {attempt_id}: {exc}")
        _discard(dest)
        return None

    if not ok or not dest.exists():
        logger.debug(f"no trace at {source!r} on {host} for attempt {attempt_id}")
        _discard(dest)
        return None

    cap = max_bytes()
    try:
        written = dest.stat().st_size
        if written > cap:
            logger.warning(
                f"trace for attempt {attempt_id} is {written} bytes, over the "
                f"{cap}-byte cap (HERMES_TRACE_MAX_MB); discarding it rather "
                f"than keeping part of it. It remains at {source!r} on {host}."
            )
            _discard(dest)
            return None
        dest.chmod(0o600)
    except OSError as exc:
        logger.warning(f"could not finish the trace for attempt {attempt_id}: {exc}")
        _discard(dest)
        return None

    logger.info(f"captured {written} bytes of trace for attempt {attempt_id}")
    return dest


def backfill(conn, *, agents, site, run_id: Optional[str] = None,
             dry_run: bool = False) -> dict:
    """Capture traces for attempts that were recorded before capture existed.

    Every run from before ``capture`` has an evidence ref and nothing behind it.
    Where the worker's transcript is still on a host this master can reach, it
    can be fetched late. Same two questions as ``capture``, asked afterwards.

    An attempts row does not say which agent produced it, and deriving one from
    the run is guesswork once a run fans across several. Refs are namespaced
    instead (``claude:session:…``), so the owning adapter is the one that claims
    the ref: each agent in ``agents`` is asked until one names a source.

    Returns a report whose counts partition ``considered``:
      * ``captured``  -- fetched and written now
      * ``already``   -- a trace was already on disk, left alone
      * ``missing``   -- claimed, but the transcript could not be fetched
      * ``unclaimed`` -- no agent recognised the ref
    ``dry_run`` fetches nothing and reports ``would_capture`` instead.
    """
    logger = log.get_logger("trace")
    report = {"considered": 0, "captured": 0, "already": 0, "missing": 0,
              "unclaimed": 0, "would_capture": 0}

    sql = (
        "SELECT a.id, a.ticket_id, a.host, a.result_ref, t.run_id "
        "FROM attempts a JOIN tickets t ON t.id = a.ticket_id "
        "WHERE a.result_ref IS NOT NULL"
    )
    params: tuple = ()
    if run_id:
        sql += " AND t.run_id = ?"
        params = (run_id,)
    sql += " ORDER BY a.id"

    for attempt_id, ticket_id, host, ref, attempt_run in conn.execute(sql, params).fetchall():
        report["considered"] += 1

        if size(attempt_run, attempt_id) is not None:
            report["already"] += 1
            continue

        # A Result carrying just enough for an agent to recognise its own ref.
        stub = Result(
            outcome="ok", termination_reason="goal_met", result_ref=ref,
            error_summary=None, started_at=0.0, ended_at=0.0,
            payload={}, evidence_ref=None,
        )
        envelope = {"ticket_id": ticket_id, "run_id": attempt_run}

        owner = None
        for candidate in agents:
            if _ask_agent(candidate, stub, envelope, logger):
                owner = candidate
                break
        if owner is None:
            report["unclaimed"] += 1
            continue

        if dry_run:
            report["would_capture"] += 1
            continue

        written = capture(
            site=site, host=host, agent=owner, result=stub, envelope=envelope,
            run_id=attempt_run, attempt_id=attempt_id,
        )
        if written is None:
            report["missing"] += 1
        else:
            report["captured"] += 1

    return report


def _ask_agent(agent, result, envelope, logger) -> Optional[str]:
    """The agent's own answer to "where is your trace", or None."""
    ask = getattr(agent, "trace_source", None)
    if not callable(ask):
        return None
    try:
        source = ask(result, envelope)
    except Exception as exc:
        logger.warning(f"agent could not name its trace: {exc}")
        return None
    if not isinstance(source, str) or not source.strip():
        return None
    return source.strip()


def _discard(path: Path) -> None:
    """Remove a partial/stale trace, saying nothing if it was never there."""
    try:
        path.unlink()
    except OSError:
        pass
