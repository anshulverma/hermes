"""
tests.unit.test_runs_list_and_needs_you — the runs rail's reads.

/api/runs order and its updated_at / has_view / subject / awaiting fields, and
the cross-run /api/needs-you list. Real SQLite in a temp HERMES_HOME; the only
fakes are a counting view_playbook and a statement-tracing connect.
"""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.db.migrate import apply_migrations
from server.app import create_app


@pytest.fixture
def temp_home(tmp_path: Path, monkeypatch):
    """A temp HERMES_HOME with migrations applied."""
    home = tmp_path / "hermes-test"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    apply_migrations(str(home / "queue.db"))
    yield home
    monkeypatch.delenv("HERMES_HOME", raising=False)


@pytest.fixture
def client(temp_home: Path):
    return TestClient(create_app())


def _db(home: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(home / "queue.db"))


def _run(conn, run_id: str, *, playbook: str = "p-one", created_at: float = 100.0,
         updated_at: float | None = None) -> None:
    conn.execute(
        """INSERT INTO runs
           (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES (?, ?, 'local', 'running', 'work', 'main', '{}', ?, ?)""",
        (run_id, playbook, created_at, created_at if updated_at is None else updated_at),
    )


def _ticket(conn, ticket_id: str, run_id: str, state: str = "queued",
            payload: dict | None = None) -> None:
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, payload_json, created_at, updated_at)
           VALUES (?, ?, 'work', ?, ?, 0, 0)""",
        (ticket_id, run_id, state, json.dumps(payload or {})),
    )


def _reduction(conn, run_id: str, doc: dict | str, *, review_state: str = "pending",
               created_at: float = 0.0) -> int:
    raw = doc if isinstance(doc, str) else json.dumps(doc)
    cur = conn.execute(
        """INSERT INTO reductions (run_id, phase, kind, json, review_state, created_at, updated_at)
           VALUES (?, 'work', 'turn', ?, ?, ?, ?)""",
        (run_id, raw, review_state, created_at, created_at),
    )
    return cur.lastrowid


def test_runs_list_orders_newest_first_and_breaks_ties_by_id_descending(client, temp_home):
    conn = _db(temp_home)
    _run(conn, "r-a", created_at=100.0)
    _run(conn, "r-b", created_at=100.0)
    _run(conn, "r-c", created_at=200.0)
    conn.commit()
    conn.close()

    ids = [run["id"] for run in client.get("/api/runs").json()]

    assert ids == ["r-c", "r-b", "r-a"]


def test_runs_list_carries_updated_at_has_view_subject_and_awaiting(client, temp_home):
    conn = _db(temp_home)
    _run(conn, "r-1", playbook="no-such-playbook", created_at=100.0, updated_at=250.5)
    _ticket(conn, "r-1/t-9", "r-1", "queued", {"title": "Seeded first"})
    _ticket(conn, "r-1/t-0", "r-1", "queued", {"title": "Seeded second"})
    conn.commit()
    conn.close()

    [run] = client.get("/api/runs").json()

    assert set(run) == {
        "id", "playbook", "site", "state", "phase", "base_ref", "created_at",
        "tickets", "updated_at", "has_view", "subject", "awaiting",
    }
    assert run["updated_at"] == 250.5
    assert isinstance(run["updated_at"], float)
    assert run["created_at"] == 100.0
    assert run["has_view"] is False
    # The lowest-rowid ticket, not the lowest id: t-9 was inserted first.
    assert run["subject"] == "Seeded first"
    assert run["awaiting"] == 0
    assert run["tickets"] == {"queued": 2}


def test_runs_list_subject_is_the_first_tickets_heading_or_null(client, temp_home):
    conn = _db(temp_home)
    _run(conn, "r-none", created_at=100.0)
    _run(conn, "r-blank", created_at=200.0)
    _ticket(conn, "r-blank/t-0", "r-blank", "queued", {})
    _run(conn, "r-goal", created_at=300.0)
    _ticket(conn, "r-goal/t-0", "r-goal", "queued", {"goal": "Fix the flake\nand say why"})
    conn.commit()
    conn.close()

    data = client.get("/api/runs").json()
    subjects = {run["id"]: run["subject"] for run in data}

    assert subjects == {"r-none": None, "r-blank": None, "r-goal": "Fix the flake"}
    assert {run["id"]: run["tickets"] for run in data}["r-none"] == {}


def test_runs_list_computes_has_view_once_per_playbook(client, temp_home, monkeypatch):
    import server.app as app_module
    calls: list[str] = []

    def counting_view_playbook(name):
        calls.append(name)
        return object() if name == "p-view" else None

    monkeypatch.setattr(app_module, "view_playbook", counting_view_playbook)
    conn = _db(temp_home)
    for i in range(3):
        _run(conn, f"v-{i}", playbook="p-view", created_at=100.0 + i)
    for i in range(2):
        _run(conn, f"b-{i}", playbook="p-blind", created_at=200.0 + i)
    conn.commit()
    conn.close()

    data = client.get("/api/runs").json()

    assert sorted(calls) == ["p-blind", "p-view"]
    assert {run["id"]: run["has_view"] for run in data} == {
        "v-0": True, "v-1": True, "v-2": True, "b-0": False, "b-1": False,
    }


def test_runs_list_statement_count_does_not_grow_with_runs(client, temp_home, monkeypatch):
    import server.app as app_module
    real_connect = app_module.connect
    statements: list[str] = []

    def traced_connect(path):
        conn = real_connect(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(app_module, "connect", traced_connect)

    def get_runs() -> tuple[int, list[dict]]:
        statements.clear()
        response = client.get("/api/runs")
        assert response.status_code == 200
        return len(statements), response.json()

    conn = _db(temp_home)
    _run(conn, "r-0", created_at=100.0)
    _ticket(conn, "r-0/t-0", "r-0", "queued", {"title": "t"})
    conn.commit()
    one, _ = get_runs()

    for i in range(1, 5):
        _run(conn, f"r-{i}", created_at=100.0 + i)
        _ticket(conn, f"r-{i}/t-0", f"r-{i}", "running", {"title": "t"})
        _ticket(conn, f"r-{i}/t-1", f"r-{i}", "done", {"title": "t"})
        _ticket(conn, f"r-{i}/t-2", f"r-{i}", "done", {"title": "t"})
    conn.commit()
    conn.close()
    five, data = get_runs()

    assert five == one
    assert {run["id"]: run["tickets"] for run in data} == {
        "r-0": {"queued": 1},
        **{f"r-{i}": {"running": 1, "done": 2} for i in range(1, 5)},
    }


def test_runs_list_awaiting_counts_pending_reductions_holding_a_needs_human_ticket(client, temp_home):
    conn = _db(temp_home)
    _run(conn, "r-a", created_at=100.0)
    _ticket(conn, "r-a/t-0", "r-a", "queued")
    _ticket(conn, "r-a/t-1", "r-a", "needs_human")
    _ticket(conn, "r-a/t-2", "r-a", "done")
    # Awaits: pending, its needs_human_ticket_ids names a needs_human ticket.
    _reduction(conn, "r-a", {"needs_human_ticket_ids": ["r-a/t-1"]})
    # Awaits: pending, the needs_human ticket arrives through member_ticket_ids.
    _reduction(conn, "r-a", {"member_ticket_ids": ["r-a/t-0", "r-a/t-1"]})
    # Settled or replaced: never awaiting, whatever tickets they name.
    _reduction(conn, "r-a", {"needs_human_ticket_ids": ["r-a/t-1"]}, review_state="accepted")
    _reduction(conn, "r-a", {"needs_human_ticket_ids": ["r-a/t-1"]}, review_state="rejected")
    _reduction(conn, "r-a", {"needs_human_ticket_ids": ["r-a/t-1"]}, review_state="superseded")
    # Pending, but no member ticket is in needs_human.
    _reduction(conn, "r-a", {"member_ticket_ids": ["r-a/t-0", "r-a/t-2"]})
    _reduction(conn, "r-a", {"member_ticket_ids": ["r-a/t-404"]})
    _run(conn, "r-b", created_at=200.0)
    _ticket(conn, "r-b/t-0", "r-b", "queued")
    _reduction(conn, "r-b", {"member_ticket_ids": ["r-b/t-0"]})
    conn.commit()
    conn.close()

    awaiting = {run["id"]: run["awaiting"] for run in client.get("/api/runs").json()}

    assert awaiting == {"r-a": 2, "r-b": 0}


def test_needs_you_is_empty_for_an_empty_home(client, temp_home):
    response = client.get("/api/needs-you")

    assert response.status_code == 200
    assert response.json() == []


def test_needs_you_lists_waiting_decisions_across_runs_oldest_first(client, temp_home):
    conn = _db(temp_home)
    _run(conn, "r-a", playbook="p-one", created_at=100.0)
    _ticket(conn, "r-a/t-0", "r-a", "done")
    _ticket(conn, "r-a/t-1", "r-a", "needs_human")
    _run(conn, "r-b", playbook="p-two", created_at=200.0)
    _ticket(conn, "r-b/t-1", "r-b", "needs_human")
    _run(conn, "r-c", playbook="p-one", created_at=300.0)
    _ticket(conn, "r-c/t-0", "r-c", "done")
    a_late = _reduction(conn, "r-a", {"needs_human_ticket_ids": ["r-a/t-1"]}, created_at=300.0)
    b_early = _reduction(conn, "r-b", {"needs_human_ticket_ids": ["r-b/t-1"]}, created_at=100.0)
    b_tie = _reduction(conn, "r-b", {"member_ticket_ids": ["r-b/t-1"]}, created_at=300.0)
    # Excluded: settled, or pending with no member ticket in needs_human.
    _reduction(conn, "r-a", {"needs_human_ticket_ids": ["r-a/t-1"]},
               review_state="accepted", created_at=50.0)
    _reduction(conn, "r-a", {"needs_human_ticket_ids": ["r-a/t-1"]},
               review_state="rejected", created_at=60.0)
    _reduction(conn, "r-a", {"member_ticket_ids": ["r-a/t-0"]}, created_at=70.0)
    _reduction(conn, "r-c", {"member_ticket_ids": ["r-c/t-0"]}, created_at=80.0)
    conn.commit()
    conn.close()

    response = client.get("/api/needs-you")
    assert response.status_code == 200
    items = response.json()
    runs = client.get("/api/runs").json()

    # created_at ascending; the 300.0 tie goes to the lower reduction id.
    assert [(item["id"], item["run_id"], item["playbook"], item["created_at"]) for item in items] == [
        (b_early, "r-b", "p-two", 100.0),
        (a_late, "r-a", "p-one", 300.0),
        (b_tie, "r-b", "p-two", 300.0),
    ]
    # The top bar's cross-run count is the sum of the rail's awaiting.
    assert sum(run["awaiting"] for run in runs) == len(items)


def test_needs_you_item_is_the_reductions_row_plus_playbook_and_created_at(client, temp_home):
    conn = _db(temp_home)
    _run(conn, "r-a", playbook="p-one", created_at=100.0)
    _ticket(conn, "r-a/t-0", "r-a", "done")
    _ticket(conn, "r-a/t-1", "r-a", "needs_human")
    rid = _reduction(
        conn, "r-a",
        {"verdict": "ship it", "member_ticket_ids": ["r-a/t-0"],
         "needs_human_ticket_ids": ["r-a/t-1", "r-a/t-0"]},
        created_at=123.5,
    )
    conn.commit()
    conn.close()

    response = client.get("/api/needs-you")
    assert response.status_code == 200
    [item] = response.json()
    [row] = [r for r in client.get("/api/runs/r-a/reductions").json() if r["id"] == rid]

    assert item == {**row, "playbook": "p-one", "created_at": 123.5}
    assert set(item) == {
        "id", "run_id", "phase", "kind", "json", "review_state",
        "member_ticket_ids", "member_tickets", "playbook", "created_at",
    }
    assert item["member_ticket_ids"] == ["r-a/t-0", "r-a/t-1"]
    assert item["member_tickets"] == [
        {"id": "r-a/t-0", "state": "done", "phase": "work"},
        {"id": "r-a/t-1", "state": "needs_human", "phase": "work"},
    ]


def test_needs_you_needs_a_token_off_loopback(temp_home):
    from server.auth import read_token

    remote = TestClient(create_app(bind="0.0.0.0"))

    assert remote.get("/api/needs-you").status_code == 401
    token = read_token(temp_home)
    response = remote.get("/api/needs-you", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == []


def test_runs_without_a_needs_human_ticket_never_parse_their_reductions(client, temp_home, monkeypatch):
    """Output reductions stay pending forever; only a run holding a
    needs_human ticket may pay for reading its reduction JSON."""
    import server.app as app_module
    real_connect = app_module.connect
    statements: list[str] = []

    def traced_connect(path):
        conn = real_connect(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(app_module, "connect", traced_connect)
    conn = _db(temp_home)
    _run(conn, "r-out", created_at=100.0)
    _ticket(conn, "r-out/t-0", "r-out", "done")
    _reduction(conn, "r-out", "this is not json")
    conn.commit()

    runs = client.get("/api/runs")
    needs_you = client.get("/api/needs-you")

    assert runs.status_code == 200
    assert runs.json()[0]["awaiting"] == 0
    assert needs_you.status_code == 200
    assert needs_you.json() == []
    # No needs_human ticket anywhere: no statement even scans reductions.
    assert [s for s in statements if "reductions" in s] == []

    # Once another run holds one, only that run's reductions are read.
    _run(conn, "r-nh", created_at=200.0)
    _ticket(conn, "r-nh/t-0", "r-nh", "needs_human")
    _reduction(conn, "r-nh", {"needs_human_ticket_ids": ["r-nh/t-0"]})
    conn.commit()
    conn.close()

    runs = client.get("/api/runs")
    needs_you = client.get("/api/needs-you")

    assert runs.status_code == 200
    assert {r["id"]: r["awaiting"] for r in runs.json()} == {"r-out": 0, "r-nh": 1}
    assert needs_you.status_code == 200
    assert len(needs_you.json()) == 1
