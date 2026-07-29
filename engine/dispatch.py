"""
engine.dispatch — the serve + master loops (spec §5, §9, §10).

Two loops tie the engine together:

- ``serve_loop`` repeatedly drives ``transport.serve_once_for_host`` for one host
  until there is no more claimable work for it (or the run leaves ``running``).
  It is the in-process worker for the ``local`` site and the body of a remote
  ``hermes serve --host``.
- ``master_loop`` is the orchestrator. Each cycle it runs the heartbeat
  housekeeping (health re-probe, down-requeue, lease renew/reclaim) REGARDLESS of
  run state, then — ONLY while the run is ``running`` (§5 pause freeze) — drives
  the serve loops, reduces a fully-settled phase, advances to the next phase (or
  terminates the run ``done``/``failed``).

Critical correctness (the point of this slice):
- ``master_loop`` NEVER writes ``tickets``/``runs`` state directly. Every state
  transition goes through a ``queue`` writer: it drives the serve loops (which use
  ``claim_ticket``/``record_result``/...), reduces via
  ``load_findings`` → ``playbook.reduce`` → ``record_reduction`` →
  ``finish_phase_reductions``, advances via ``next_phase`` → ``set_run_phase`` +
  ``seed_tickets``, and terminates via ``set_run_state(done|failed)``.
- A ``paused``/``stopped`` run makes NO progression: no claim, no reduce, no phase
  advance, no seed, and no automatic terminal transition — only heartbeat
  housekeeping continues, so an already-dispatched ticket can still land in
  ``reducing`` and wait for ``resume``.
- The loop is bounded (``max_cycles`` or a natural terminate-when-done) so it
  never hangs.

Stdlib-only (sqlite3 + time).
"""
from __future__ import annotations

import sqlite3
import time
from typing import Optional

from engine import crew, queue, transport

# Ticket states that still count as "actionable" work in a phase: while any of
# these exist the phase is not settled and must not be reduced/advanced (§5, §9).
# ``needs_human`` blocks too (a re-verify/guard-routed or reduce-flagged ticket
# still awaits a human) and is handled separately from the pre-reduce gate.
_ACTIVE_STATES = ("queued", "dispatched", "running", "parked")


def _now(now: Optional[float]) -> float:
    return time.time() if now is None else now


def _run_state(conn: sqlite3.Connection, run_id: str) -> Optional[str]:
    row = conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
    return row[0] if row else None


# --- serve loop ----------------------------------------------------------

def serve_loop(
    conn: sqlite3.Connection,
    site,
    agent,
    host: str,
    run,
    playbook,
    base_ref: str,
    now: Optional[float] = None,
) -> int:
    """Drive ``serve_once_for_host`` for ``host`` until no claimable work (§9, §10).

    Loops while the run is ``running`` and ``serve_once_for_host`` keeps returning
    a Result (a ticket was executed + recorded). It stops as soon as ``serve_once``
    returns ``None`` — nothing claimable, an at-capacity park, a deterministic
    contract abort, or a host-lost requeue — which also guarantees termination
    (a parked/failed/transport-requeued ticket does not re-present as claimable at
    the same ``now``). ``master_loop`` re-drives on the next cycle, so any tickets
    left behind get picked up. Returns how many tickets it processed.
    """
    t = _now(now)
    processed = 0
    while True:
        if _run_state(conn, run.id) != "running":
            break
        result = transport.serve_once_for_host(
            conn, host, site, agent, run, playbook, base_ref, now=t
        )
        if result is None:
            break
        processed += 1
    return processed


# --- master loop ---------------------------------------------------------

def master_loop(
    conn: sqlite3.Connection,
    run_id: str,
    playbook,
    site,
    agent,
    base_ref: str,
    hosts,
    now: Optional[float] = None,
    max_cycles: Optional[int] = None,
) -> str:
    """Orchestrate a run to a terminal state (§5, §9, §10).

    Each cycle: (a) ``crew.heartbeat_sweep`` (always, regardless of run state);
    (b) only while the run is ``running``, drive the in-process serve loops for
    ``hosts`` and then reduce/advance/terminate the current phase. A
    ``paused``/``stopped``/terminal run makes no progression.

    Bounded by ``max_cycles`` (``None`` = run until the run reaches a terminal
    state). Returns the run's final observed state.
    """
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        t = _now(now)

        # (a) Housekeeping runs every cycle regardless of run state (§5): health
        # re-probe, down-requeue, lease renew/reclaim, un-park.
        crew.heartbeat_sweep(conn, site, agent, now=t)

        state = _run_state(conn, run_id)
        if state is None or state in ("done", "failed", "stopped"):
            # Terminal (or a stopped run makes no progression): nothing to drive.
            return state
        if state != "running":
            # paused: only housekeeping continues (pause freeze, §5).
            continue

        # (b) Progression — running only. Drive the serve loops for each host.
        run = queue._load_run(conn, run_id)
        for host in hosts:
            serve_loop(conn, site, agent, host, run, playbook, base_ref, now=t)

        # Reduce a fully-settled phase and advance / terminate.
        if _reduce_and_advance(conn, run_id, playbook, site, now=t):
            return _run_state(conn, run_id)

    return _run_state(conn, run_id)


# --- reduce + advance (all writes via queue seam) ------------------------

def _reduce_and_advance(
    conn: sqlite3.Connection, run_id: str, playbook, site, now: float
) -> bool:
    """Reduce the current phase if settled, then advance or terminate (§9).

    Returns True iff the run reached a terminal state (``done``/``failed``) this
    call, so ``master_loop`` can stop. Every state write goes through a ``queue``
    writer — this function only ORCHESTRATES.
    """
    run = queue._load_run(conn, run_id)
    phase = run.phase
    counts = queue.phase_ticket_counts(conn, run_id, phase)
    active = sum(counts.get(s, 0) for s in _ACTIVE_STATES)
    nh = counts.get("needs_human", 0)

    if active > 0:
        # Phase still working; the serve loop will progress it on a later cycle.
        return False
    if nh > 0:
        # Blocked awaiting a human decision (re-verify/guard-routed); do not
        # reduce or advance (§5 needs_human blocks advancement).
        return False

    # active == 0 and nh == 0: the phase has settled into reducing/failed. Reduce
    # once (guarded so a re-visit after a reduce-flagged needs_human is settled
    # never double-reduces).
    if not _phase_reduced(conn, run_id, phase):
        _do_reduce(conn, run_id, playbook, site, phase, now)
        counts = queue.phase_ticket_counts(conn, run_id, phase)
        nh = counts.get("needs_human", 0)

    reducing = counts.get("reducing", 0)
    if nh > 0 or reducing > 0:
        # reduce flagged tickets to needs_human (blocks) or left some reducing.
        return False

    # Phase fully settled (done/failed only). Advance or terminate.
    run = queue._load_run(conn, run_id)  # reductions = this phase's, for next_phase
    nxt = playbook.next_phase(run)
    if nxt is not None:
        queue.set_run_phase(conn, run_id, nxt, now=now)
        # Reload so the snapshot carries phase=nxt and the PRIOR phase's
        # reductions (§9); seed builds phase-N tickets from phase-(N-1) output.
        next_run = queue._load_run(conn, run_id)
        queue.seed_tickets(conn, next_run, playbook, site)
        return False

    if playbook.is_done(run):
        queue.set_run_state(conn, run_id, "done", now=now)
        return True

    # Stuck: no next phase, not done, and no actionable tickets remain (§5).
    queue.set_run_state(conn, run_id, "failed", now=now)
    return True


def _do_reduce(
    conn: sqlite3.Connection, run_id: str, playbook, site, phase: str, now: float
) -> None:
    """Run the REDUCE step for a settled phase via the queue seam (§9)."""
    run = queue._load_run(conn, run_id)
    findings = queue.load_findings(conn, run_id, phase)
    reductions = playbook.reduce(run, phase, findings, site)
    for reduction in reductions:
        queue.record_reduction(conn, run_id, phase, reduction, now=now)
    queue.finish_phase_reductions(conn, run_id, phase, now=now)


def _phase_reduced(conn: sqlite3.Connection, run_id: str, phase: str) -> bool:
    """True iff a reduction has already been recorded for this phase (§9).

    Guards against re-reducing a phase across cycles (e.g. after a reduce-flagged
    ``needs_human`` ticket is later settled by an operator).
    """
    row = conn.execute(
        "SELECT COUNT(*) FROM reductions WHERE run_id=? AND phase=?",
        (run_id, phase),
    ).fetchone()
    return row[0] > 0
