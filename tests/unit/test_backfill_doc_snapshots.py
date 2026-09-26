"""The run-9 backfill: replay recorded Edit calls, write doc/ snapshots or nothing.

Everything runs against a synthetic run -- a real migrated queue.db, real
JSONL traces in the shape Claude Code writes, a real git repo holding the
original -- never against the operator's home.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from engine.db.migrate import apply_migrations, connect
from playbooks.committee.replay import ReplayError, apply_edits, edit_calls

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_doc_snapshots.py"
_spec = importlib.util.spec_from_file_location("backfill_doc_snapshots", _SCRIPT)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)

RUN = "run-7"
ARTIFACT = "/host/repo/docs/plan.md"               # recorded, never opened
REVISED = "/host/home/runs/run-7/revised/plan.md"  # the path the junior edited
ORIGINAL = "# Plan\n\nStaff six engineers.\nShip in Q3.\nShip in Q3.\n"
AFTER_T03 = "# Plan\n\nStaff two engineers.\nShip in Q3.\nShip in Q3.\n"
FINAL = "# Plan\n\nStaff two engineers.\nShip in Q4.\nShip in Q4.\n"
TABLES = ("runs", "tickets", "attempts", "reductions", "events")


def _edit(call_id, old, new, *, target=REVISED, replace_all=False, name="Edit"):
    return {"type": "tool_use", "id": call_id, "name": name,
            "input": {"file_path": target, "old_string": old, "new_string": new,
                      "replace_all": replace_all}}


def _write_trace(path: Path, calls, errors=()):
    """One assistant line per tool_use, then one user line carrying every result."""
    lines = [json.dumps({"type": "assistant", "message": {"content": [c]}}) for c in calls]
    results = [
        {"type": "tool_result", "tool_use_id": c["id"], "content": "done",
         **({"is_error": True} if c["id"] in errors else {})}
        for c in calls
    ]
    lines.append(json.dumps({"type": "user", "message": {"content": results}}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


STAFF = _edit("toolu_staff", "Staff six engineers.", "Staff two engineers.")
SHIP_ALL = _edit("toolu_ship", "Ship in Q3.", "Ship in Q4.", replace_all=True)


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    apply_migrations(str(home / "queue.db"))
    return home


@pytest.fixture(autouse=True)
def repo(tmp_path, monkeypatch):
    """The original at HEAD of a real repo; the script reads it from its cwd."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "plan.md").write_text(ORIGINAL, encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for argv in (["git", "init", "-q"], ["git", "add", "."],
                 ["git", "commit", "-q", "-m", "plan"]):
        subprocess.run(argv, cwd=repo, check=True, env=env)
    monkeypatch.chdir(repo)
    return repo


def _seed(home, attempts=None, *, verified=None, final=FINAL, errors=()):
    """t01 reviewer, t02 owner, t03 junior, t04 reviewer, t05 owner, t06 junior.

    ``attempts`` maps a junior turn to its attempts, each a list of tool calls,
    replayed in attempt-id order.
    """
    attempts = attempts if attempts is not None else {3: [[STAFF]], 6: [[SHIP_ALL]]}
    verified = verified or {3: True, 6: True}
    roles = {1: "senior_director", 2: "owner", 3: "junior_ic",
             4: "manager", 5: "owner", 6: "junior_ic"}
    conn = connect(str(home / "queue.db"))
    try:
        conn.execute(
            "INSERT INTO runs (id, playbook, site, base_ref, config_json, state, phase,"
            " created_at, updated_at) VALUES (?, 'committee', 'local', 'main', '{}',"
            " 'done', 'ruling', 0, 0)", (RUN,))
        for turn, role in roles.items():
            doc = {"turn": turn, "role": role, "delivered": True,
                   "delegate": role == "owner",
                   "verified": verified.get(turn) if role == "junior_ic" else None,
                   "artifact": ARTIFACT, "revised": REVISED}
            conn.execute(
                "INSERT INTO reductions (run_id, phase, kind, json, review_state,"
                " created_at, updated_at) VALUES (?, ?, 'turn', ?, 'pending', 0, 0)",
                (RUN, f"t{turn:02d}-{role}", json.dumps(doc)))
        attempt_id = 100
        for turn, runs_of_calls in attempts.items():
            ticket = f"{RUN}/t{turn:02d}-junior_ic"
            conn.execute(
                "INSERT INTO tickets (id, run_id, phase, state, created_at, updated_at)"
                " VALUES (?, ?, ?, 'done', 0, 0)", (ticket, RUN, f"t{turn:02d}-junior_ic"))
            for calls in runs_of_calls:
                attempt_id += 1
                conn.execute(
                    "INSERT INTO attempts (id, ticket_id, phase, host, attempt)"
                    " VALUES (?, ?, ?, 'localhost', 1)",
                    (attempt_id, ticket, f"t{turn:02d}-junior_ic"))
                _write_trace(home / "runs" / RUN / "traces" / f"{attempt_id}.jsonl",
                             calls, errors)
        conn.commit()
    finally:
        conn.close()
    revised = home / "runs" / RUN / "revised" / "plan.md"
    revised.parent.mkdir(parents=True, exist_ok=True)
    revised.write_text(final, encoding="utf-8")


def _counts(home):
    conn = sqlite3.connect(home / "queue.db")
    try:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally:
        conn.close()


def _run(*extra):
    return backfill.main(["--run", RUN, "--rev", "HEAD", "--path", "docs/plan.md", *extra])


# --- replay.py: pure --------------------------------------------------------

def test_edit_calls_keeps_the_successful_edits_on_the_target_in_order(tmp_path):
    first = _edit("a", "x", "y")
    elsewhere = _edit("b", "x", "y", target="/some/other/file.md")
    failed = _edit("c", "y", "z")
    last = _edit("d", "y", "w")
    trace = tmp_path / "t.jsonl"
    # `first` twice: a trace can repeat a message, and ids dedupe it.
    _write_trace(trace, [first, elsewhere, first, failed, last], errors=("c",))

    assert [call["id"] for call in edit_calls(trace, REVISED)] == ["a", "d"]


@pytest.mark.parametrize("call", [
    _edit("w", "", "everything", name="Write"),
    _edit("m", "x", "y", name="MultiEdit"),
    {"type": "tool_use", "id": "n", "name": "NotebookEdit",
     "input": {"notebook_path": REVISED, "new_source": "x"}},
], ids=["Write", "MultiEdit", "NotebookEdit"])
def test_a_tool_that_cannot_be_replayed_on_the_target_is_refused(tmp_path, call):
    trace = tmp_path / "t.jsonl"
    _write_trace(trace, [call])

    with pytest.raises(ReplayError, match="cannot be replayed"):
        edit_calls(trace, REVISED)


def test_apply_edits_replaces_one_occurrence_or_every_one_with_replace_all():
    data = ORIGINAL.encode()
    assert apply_edits(data, [STAFF]) == AFTER_T03.encode()
    assert apply_edits(apply_edits(data, [STAFF]), [SHIP_ALL]) == FINAL.encode()


@pytest.mark.parametrize("call", [
    _edit("amb", "Ship in Q3.", "Ship in Q4."),                     # twice, not replace_all
    _edit("gone", "Staff nine engineers.", "x"),                    # not there at all
    _edit("gone-all", "Ship in Q9.", "x", replace_all=True),        # replace_all of nothing
], ids=["ambiguous", "absent", "replace_all-absent"])
def test_apply_edits_refuses_an_old_string_that_is_not_exactly_where_it_was(call):
    with pytest.raises(ReplayError):
        apply_edits(ORIGINAL.encode(), [call])


# --- the script ---------------------------------------------------------------

def test_a_backfill_writes_every_version_and_changes_no_row(home, capsys):
    _seed(home)
    before = _counts(home)

    assert _run() == 0

    doc = home / "runs" / RUN / "doc"
    assert sorted(p.name for p in doc.iterdir()) == ["00-original.md", "t03.md", "t06.md"]
    assert (doc / "00-original.md").read_text() == ORIGINAL
    assert (doc / "t03.md").read_text() == AFTER_T03
    assert (doc / "t06.md").read_text() == FINAL
    assert doc.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in doc.iterdir())
    assert not (home / "runs" / RUN / ".doc-tmp").exists()
    out = capsys.readouterr().out.splitlines()
    assert out[:2] == ["t03 -1/+1", "t06 -2/+2"]
    assert out[2].startswith("final sha256 ")
    assert _counts(home) == before


def test_an_edit_the_tool_refused_is_not_replayed(home):
    bad = _edit("toolu_bad", "Ship in Q3.", "Ship never.")  # ambiguous: the tool refused it
    _seed(home, {3: [[bad, STAFF]], 6: [[SHIP_ALL]]}, errors=("toolu_bad",))

    assert _run() == 0
    assert (home / "runs" / RUN / "doc" / "t03.md").read_text() == AFTER_T03


def test_every_attempt_on_a_junior_ticket_replays_in_attempt_order(home):
    five = _edit("toolu_five", "Staff six engineers.", "Staff five engineers.")
    two = _edit("toolu_two", "Staff five engineers.", "Staff two engineers.")
    _seed(home, {3: [[five], [two]], 6: [[SHIP_ALL]]})

    assert _run() == 0
    assert (home / "runs" / RUN / "doc" / "t03.md").read_text() == AFTER_T03


def test_an_ambiguous_old_string_aborts_and_writes_nothing(home, capsys):
    once = _edit("toolu_once", "Ship in Q3.", "Ship in Q4.")  # two matches, no replace_all
    _seed(home, {3: [[STAFF]], 6: [[once]]})

    assert _run() == 1
    assert not (home / "runs" / RUN / "doc").exists()
    assert "expected exactly one" in capsys.readouterr().err


def test_a_write_on_the_target_aborts_and_writes_nothing(home):
    _seed(home, {3: [[_edit("toolu_w", "", FINAL, name="Write")]], 6: [[SHIP_ALL]]})

    assert _run() == 1
    assert not (home / "runs" / RUN / "doc").exists()


@pytest.mark.parametrize("attempts, verified, final, message", [
    ({3: [[]], 6: [[STAFF, SHIP_ALL]]}, {3: True, 6: True}, FINAL,
     "t03 was verified but its edits changed nothing"),
    ({3: [[STAFF]], 6: [[SHIP_ALL]]}, {3: True, 6: False}, FINAL,
     "t06 did not apply but its edits changed the document"),
], ids=["verified-but-unchanged", "unverified-but-changed"])
def test_a_replay_that_contradicts_a_recheck_aborts(home, capsys, attempts, verified, final, message):
    _seed(home, attempts, verified=verified, final=final)

    assert _run() == 1
    assert message in capsys.readouterr().err
    assert not (home / "runs" / RUN / "doc").exists()


def test_a_replay_that_does_not_reproduce_the_revised_copy_aborts(home, capsys):
    _seed(home, final=FINAL + "a line no trace ever wrote\n")

    assert _run() == 1
    assert "byte for byte" in capsys.readouterr().err
    assert not (home / "runs" / RUN / "doc").exists()


@pytest.mark.parametrize("attempts, path, drop_trace, message", [
    (None, "docs/other.md", False, "is not the reviewed"),
    (None, "docs/plan.md", True, "no trace for attempt"),    # 101.jsonl is t03's
    ({3: [[STAFF]]}, "docs/plan.md", False, "t06 has no attempts"),
], ids=["wrong-path", "missing-trace", "no-attempts"])
def test_a_backfill_that_cannot_find_its_inputs_aborts(
    home, capsys, attempts, path, drop_trace, message
):
    _seed(home, attempts)
    if drop_trace:
        (home / "runs" / RUN / "traces" / "101.jsonl").unlink()

    assert backfill.main(["--run", RUN, "--rev", "HEAD", "--path", path]) == 1
    assert message in capsys.readouterr().err
    assert not (home / "runs" / RUN / "doc").exists()


def test_an_existing_doc_directory_is_never_overwritten(home, capsys):
    _seed(home)
    (home / "runs" / RUN / "doc").mkdir()

    assert _run() == 1
    assert "already exists" in capsys.readouterr().err
    assert list((home / "runs" / RUN / "doc").iterdir()) == []


def test_a_failed_write_leaves_neither_doc_nor_the_temp_directory(home, capsys, monkeypatch):
    """Every check passed; the second file's write fails. Nothing is left behind."""
    _seed(home)
    created = []
    real_open = os.open

    def flaky(path, flags, *args, **kwargs):
        if flags & os.O_CREAT:
            created.append(path)
            if len(created) == 2:
                raise OSError("disk full")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(backfill.os, "open", flaky)

    assert _run() == 1
    assert len(created) == 2
    assert "backfill: aborted, nothing written: disk full" in capsys.readouterr().err
    assert not (home / "runs" / RUN / "doc").exists()
    assert not (home / "runs" / RUN / ".doc-tmp").exists()


def test_every_failure_before_a_write_is_one_aborted_line_not_a_traceback(
    home, capsys, monkeypatch
):
    """A networked home (ConfigError) and a trace that is not UTF-8 (ValueError)."""
    from engine import config

    _seed(home)
    (home / "runs" / RUN / "traces" / "101.jsonl").write_bytes(b"\xff\xfe not utf-8\n")
    assert _run() == 1
    assert "backfill: aborted, nothing written: " in capsys.readouterr().err

    monkeypatch.setattr(config, "_default_networked_check", lambda path: True)
    assert _run() == 1
    assert "backfill: aborted, nothing written: HERMES_HOME must not be on a networked" \
        in capsys.readouterr().err
    assert not (home / "runs" / RUN / "doc").exists()


def test_the_database_uri_survives_a_home_with_uri_characters(tmp_path):
    """?, # and % in the home are path characters, not URI syntax -- and `?`
    must not swallow mode=ro."""
    odd = tmp_path / "homes" / "a?b#c%41 d"
    odd.mkdir(parents=True)
    apply_migrations(str(odd / "queue.db"))

    conn = backfill.open_db(odd)
    try:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone() == (0,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO events (ts, kind) VALUES (0, 'x')")
    finally:
        conn.close()
    assert [p.name for p in odd.parent.iterdir()] == ["a?b#c%41 d"]  # no stray file "a"


def test_a_dry_run_prints_every_step_and_writes_nothing(home, capsys):
    _seed(home)

    assert _run("--dry-run") == 0
    assert capsys.readouterr().out.splitlines()[:2] == ["t03 -1/+1", "t06 -2/+2"]
    assert not (home / "runs" / RUN / "doc").exists()
    assert not (home / "runs" / RUN / ".doc-tmp").exists()


def test_the_database_is_opened_read_only(home):
    conn = backfill.open_db(home)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO events (ts, kind) VALUES (0, 'x')")
    finally:
        conn.close()
