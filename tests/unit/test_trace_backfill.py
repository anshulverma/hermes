"""Tests for engine.trace.backfill: capturing traces for attempts already recorded.

TDD: written FIRST, watched fail, then engine/trace.py grew backfill().

Capture happens at result time, so every run recorded before that exists has an
evidence ref and no trace behind it. Where the worker's transcript is still on a
host the master can reach, it can be fetched late -- with exactly the same two
questions capture asks, so nothing new can go wrong here that could not go wrong
there.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from engine import trace
from engine.db.migrate import apply_migrations, connect


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def db(home):
    path = str(home / "queue.db")
    apply_migrations(path)
    conn = connect(path)
    yield conn
    conn.close()


def _seed(conn, *, run_id="r1", ticket="r1/t-0", refs=("claude:session:abc",),
          site="local", state="done"):
    conn.execute(
        """INSERT OR IGNORE INTO runs (id, playbook, site, base_ref, config_json,
                                       state, phase, created_at, updated_at)
           VALUES (?, 'example', ?, 'main', '{}', ?, 'work', 0, 0)""",
        (run_id, site, state),
    )
    conn.execute(
        """INSERT OR IGNORE INTO tickets (id, run_id, phase, state, resource_req,
                                          priority, attempts, available_at,
                                          tried_hosts, payload_json, created_at, updated_at)
           VALUES (?, ?, 'work', 'done', 'cpu', 0, 0, 0, '[]', '{}', 0, 0)""",
        (ticket, run_id),
    )
    ids = []
    for n, ref in enumerate(refs, start=1):
        cur = conn.execute(
            """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at,
                                     ended_at, outcome, termination_reason,
                                     result_ref, error_summary, error_detail)
               VALUES (?, 'work', 'h1', ?, 0, 1, 'ok', 'goal_met', ?, NULL, NULL)""",
            (ticket, n, ref),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


class _Agent:
    """Claims refs in its own namespace and no others."""

    name = "fake"

    def trace_source(self, result, envelope):
        ref = result.result_ref
        if isinstance(ref, str) and ref.startswith("claude:session:"):
            return f"/traces/{ref.split(':')[-1]}.jsonl"
        return None


class _OtherAgent:
    name = "other"

    def trace_source(self, result, envelope):
        return None


class _Site:
    name = "local"

    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def fetch_file(self, host, source, dest):
        self.calls.append((host, source))
        if not self.ok:
            return False
        Path(dest).write_text('{"type":"user"}\n')
        return True


def test_backfill_captures_a_trace_for_an_attempt_that_had_none(db, home):
    [attempt_id] = _seed(db)

    report = trace.backfill(db, agents=[_Agent()], site=_Site())

    assert report["captured"] == 1
    assert trace.read("r1", attempt_id) == '{"type":"user"}\n'


def test_backfill_leaves_an_existing_trace_alone(db, home):
    [attempt_id] = _seed(db)
    path = trace.trace_path("r1", attempt_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("already here\n")

    report = trace.backfill(db, agents=[_Agent()], site=_Site())

    assert report["captured"] == 0
    assert report["already"] == 1
    assert trace.read("r1", attempt_id) == "already here\n"


def test_backfill_asks_every_agent_until_one_claims_the_ref(db, home):
    """An attempt does not record which agent ran it, and refs are namespaced --
    so the owning adapter is found by asking, not by guessing from the run."""
    [attempt_id] = _seed(db)
    site = _Site()

    report = trace.backfill(db, agents=[_OtherAgent(), _Agent()], site=site)

    assert report["captured"] == 1
    assert site.calls == [("h1", "/traces/abc.jsonl")]


def test_a_ref_no_agent_claims_is_counted_as_unclaimed(db, home):
    _seed(db, refs=("s3://somewhere/else.json",))

    report = trace.backfill(db, agents=[_Agent()], site=_Site())

    assert report["captured"] == 0
    assert report["unclaimed"] == 1


def test_a_transcript_that_is_gone_is_counted_as_missing(db, home):
    _seed(db)

    report = trace.backfill(db, agents=[_Agent()], site=_Site(ok=False))

    assert report["captured"] == 0
    assert report["missing"] == 1


def test_attempts_with_no_ref_are_not_considered(db, home):
    _seed(db, refs=(None,))

    report = trace.backfill(db, agents=[_Agent()], site=_Site())

    assert report["considered"] == 0


def test_backfill_can_be_restricted_to_one_run(db, home):
    _seed(db, run_id="r1", ticket="r1/t-0")
    _seed(db, run_id="r2", ticket="r2/t-0")

    report = trace.backfill(db, agents=[_Agent()], site=_Site(), run_id="r2")

    assert report["considered"] == 1
    assert report["captured"] == 1


def test_dry_run_reports_without_fetching_anything(db, home):
    [attempt_id] = _seed(db)
    site = _Site()

    report = trace.backfill(db, agents=[_Agent()], site=site, dry_run=True)

    assert report["would_capture"] == 1
    assert report["captured"] == 0
    assert site.calls == []
    assert trace.read("r1", attempt_id) is None


def test_backfill_covers_every_attempt_of_a_retried_ticket(db, home):
    ids = _seed(db, refs=("claude:session:aaa", "claude:session:bbb"))

    report = trace.backfill(db, agents=[_Agent()], site=_Site())

    assert report["captured"] == 2
    assert all(trace.read("r1", i) is not None for i in ids)


def test_one_failure_does_not_stop_the_rest(db, home):
    ids = _seed(db, refs=("claude:session:aaa", "claude:session:bbb"))

    class Flaky(_Site):
        def fetch_file(self, host, source, dest):
            if "aaa" in source:
                raise OSError("host went away")
            return super().fetch_file(host, source, dest)

    report = trace.backfill(db, agents=[_Agent()], site=Flaky())

    assert report["captured"] == 1
    assert report["missing"] == 1
    assert trace.read("r1", ids[1]) is not None


def test_an_agent_with_no_trace_source_is_simply_not_an_owner(db, home):
    class Mute:
        name = "mute"

    _seed(db)

    report = trace.backfill(db, agents=[Mute()], site=_Site())

    assert report["unclaimed"] == 1


def test_report_totals_add_up(db, home):
    _seed(db, run_id="r1", ticket="r1/t-0",
          refs=("claude:session:aaa", "s3://elsewhere", "claude:session:ccc"))

    report = trace.backfill(db, agents=[_Agent()], site=_Site())

    assert report["considered"] == 3
    assert (report["captured"] + report["already"] + report["missing"]
            + report["unclaimed"]) == report["considered"]
