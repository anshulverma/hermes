"""How a finished last phase settles the run."""
import threading

import pytest

from engine import dispatch, queue
from engine.db.migrate import apply_migrations, connect


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    path = str(tmp_path / "queue.db")
    apply_migrations(path)
    c = connect(path)
    yield c
    c.close()


def _run(conn, run_id="r", state="running", phase="only", playbook="p"):
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, ?, 'local', 'HEAD', '{}', ?, ?, 0, 0)""",
        (run_id, playbook, state, phase),
    )
    conn.commit()


def _ticket(conn, n, state, run_id="r", phase="only", reduction_id=None):
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, reduction_id,
                                created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, 0)""",
        (f"{run_id}/t-{n}", run_id, phase, state, reduction_id),
    )
    conn.commit()


def _pending_reduction(conn, run_id="r", phase="only"):
    cur = conn.execute(
        """INSERT INTO reductions (run_id, kind, json, phase, created_at, updated_at)
           VALUES (?, 'cluster', '{}', ?, 0, 0)""",
        (run_id, phase),
    )
    conn.commit()
    return cur.lastrowid


class _OnePhase:
    """A one-phase playbook whose ``is_done`` always says yes, as dexter's does."""

    phases = ["only"]

    def reduce(self, run, phase, findings, site):
        return []

    def next_phase(self, run):
        return None

    def is_done(self, run):
        return True


def _loop(conn, cycles, **kw):
    """Drive the real master loop with no crew and no hosts."""
    return dispatch.master_loop(
        conn, "r", _OnePhase(), None, None, "HEAD", hosts=kw.pop("hosts", []),
        now=1.0, max_cycles=cycles, stop_event=threading.Event(), **kw,
    )


# --- how a finished last phase settles the run ---------------------------

def _clusters(conn, n):
    """n tickets, each routed to needs_human by its own reduction (dexter's shape)."""
    _run(conn)
    rids = []
    for i in range(n):
        rid = _pending_reduction(conn)
        _ticket(conn, i, "needs_human", reduction_id=rid)
        rids.append(rid)
    return rids


def test_rejecting_every_cluster_fails_the_run(conn):
    for rid in _clusters(conn, 3):
        queue.reject_reduction(conn, rid)

    assert _loop(conn, 1) == "failed"


def test_accepting_some_clusters_finishes_the_run(conn):
    first, *rest = _clusters(conn, 3)
    queue.reject_reduction(conn, first)
    for rid in rest:
        queue.accept_reduction(conn, rid)

    assert _loop(conn, 1) == "done"


def test_a_last_phase_with_no_tickets_still_defers_to_is_done(conn):
    _run(conn)

    assert _loop(conn, 1) == "done"
