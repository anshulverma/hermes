"""master_loop's idle back-off, how a finished last phase settles the run, and
the CLI's opt-in ``--wait`` (on ``run <playbook>`` and ``run resume``)."""
import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from engine import dispatch, queue
from engine.cli import main
from engine.db.migrate import apply_migrations, connect
from testkit.fixtures import write_canned_issues


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


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(dispatch.time, "sleep", calls.append)
    return calls


# --- idle back-off -------------------------------------------------------

def test_a_run_waiting_on_a_human_sleeps_once_per_idle_cycle(conn, sleeps):
    _run(conn)
    _ticket(conn, 0, "needs_human")

    assert _loop(conn, 3, idle_sleep_s=0.25) == "running"
    assert sleeps == [0.25, 0.25, 0.25]


def test_the_default_never_sleeps(conn, sleeps):
    _run(conn)
    _ticket(conn, 0, "needs_human")

    assert _loop(conn, 3) == "running"
    assert sleeps == []


def test_a_cycle_that_served_a_ticket_does_not_sleep(conn, sleeps, monkeypatch):
    _run(conn)
    _ticket(conn, 0, "needs_human")
    served = iter([1, 0])
    monkeypatch.setattr(dispatch, "serve_loop", lambda *a, **k: next(served))

    _loop(conn, 2, idle_sleep_s=0.25, hosts=["h"])

    assert sleeps == [0.25]  # only the second cycle, which served nothing


def test_a_paused_run_sleeps_instead_of_spinning(conn, sleeps):
    _run(conn, state="paused")

    assert _loop(conn, 2, idle_sleep_s=0.25) == "paused"
    assert sleeps == [0.25, 0.25]


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


# --- the CLI's --wait ----------------------------------------------------

def _git_repo(path):
    """A one-commit repo on ``main`` for the local site to worktree from."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True, env=env)
    (path / "README").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True, env=env)
    return path


@pytest.fixture
def cli_home(tmp_path, monkeypatch):
    import sites.local.site  # noqa: F401
    import testkit.example_playbook  # noqa: F401
    import testkit.mock_agent  # noqa: F401

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_REPO", str(_git_repo(tmp_path / "src")))
    write_canned_issues(home / "issues" / "bug.json")
    path = str(home / "queue.db")
    apply_migrations(path)
    return path


@pytest.fixture
def loop_calls(monkeypatch):
    calls = []

    def fake(**kw):
        calls.append(kw)
        return "running"

    monkeypatch.setattr(dispatch, "master_loop", fake)
    return calls


def _state(path, run_id):
    c = connect(path)
    try:
        return c.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]
    finally:
        c.close()


def test_run_without_wait_keeps_its_bounded_loop(cli_home, loop_calls, capsys):
    assert main(["run", "example", "--site", "local", "--agent", "mock"]) == 0

    (call,) = loop_calls
    assert call["max_cycles"] == 1000
    assert call["idle_sleep_s"] == 0.0


def test_run_wait_loops_until_the_run_settles(cli_home, loop_calls, capsys):
    assert main(["run", "example", "--site", "local", "--agent", "mock", "--wait"]) == 0

    (call,) = loop_calls
    assert call["max_cycles"] is None
    assert call["idle_sleep_s"] == 1.0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == (
        f"Run {call['run_id']} is still running; "
        f"`hermes run resume {call['run_id']} --wait` picks it up again"
    )


@pytest.mark.parametrize("state", ["running", "paused"])
def test_resume_wait_drives_the_run_it_names(cli_home, loop_calls, state):
    c = connect(cli_home)
    _run(c, run_id="r1", state=state, phase="work", playbook="example")
    c.close()

    assert main(["run", "resume", "r1", "--wait", "--agent", "mock"]) == 0

    (call,) = loop_calls
    # Playbook, site and base ref all come from the run itself.
    assert (call["run_id"], call["base_ref"]) == ("r1", "HEAD")
    assert call["playbook"].name == "example"
    assert call["site"].name == "local"
    assert call["max_cycles"] is None
    assert call["idle_sleep_s"] == 1.0
    assert _state(cli_home, "r1") == "running"


def test_resume_wait_takes_a_site_given_on_the_command_line(cli_home, loop_calls, monkeypatch):
    from engine import site as site_module
    from sites.local.site import LocalSite

    elsewhere = LocalSite()
    monkeypatch.setitem(site_module._REGISTRY, "elsewhere", elsewhere)
    c = connect(cli_home)
    _run(c, run_id="r1", phase="work", playbook="example")
    c.close()

    assert main(["run", "resume", "r1", "--wait", "--agent", "mock", "--site", "elsewhere"]) == 0

    (call,) = loop_calls
    assert call["site"] is elsewhere


def test_plain_resume_of_a_running_run_is_still_an_error(cli_home, loop_calls):
    c = connect(cli_home)
    _run(c, run_id="r1", phase="work", playbook="example")
    c.close()

    assert main(["run", "resume", "r1"]) == 1
    assert loop_calls == []


def test_resume_wait_refuses_a_finished_run(cli_home, loop_calls):
    c = connect(cli_home)
    _run(c, run_id="r1", state="done", phase="work", playbook="example")
    c.close()

    assert main(["run", "resume", "r1", "--wait", "--agent", "mock"]) == 1
    assert loop_calls == []
    assert _state(cli_home, "r1") == "done"


@pytest.mark.parametrize("action", ["pause", "stop", "reopen"])
def test_wait_only_goes_with_resume(cli_home, loop_calls, action, capsys):
    c = connect(cli_home)
    _run(c, run_id="r1", state="stopped" if action == "reopen" else "running",
         phase="work", playbook="example")
    before = c.execute("SELECT state FROM runs").fetchone()[0]
    c.close()

    assert main(["run", action, "r1", "--wait"]) == 1
    assert loop_calls == []
    assert _state(cli_home, "r1") == before
    assert "--wait" in capsys.readouterr().err


def test_ctrl_c_during_wait_leaves_the_run_resumable(tmp_path):
    """A real SIGINT: exit 0, no traceback, one line saying how to pick it back up."""
    home = tmp_path / "home"
    home.mkdir()
    path = str(home / "queue.db")
    apply_migrations(path)
    c = connect(path)
    _run(c, run_id="r1", phase="work", playbook="example")
    _ticket(c, 0, "needs_human", run_id="r1", phase="work",
            reduction_id=_pending_reduction(c, run_id="r1", phase="work"))
    c.close()

    repo = _git_repo(tmp_path / "src")
    env = {**os.environ, "HERMES_HOME": str(home), "HERMES_REPO": str(repo)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "engine.cli", "run", "resume", "r1", "--wait",
         "--agent", "mock"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        # The handlers are installed before the host is admitted, so once the
        # crew row exists a Ctrl-C lands on the loop, not on a bare interpreter.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and proc.poll() is None:
            c = connect(path)
            admitted = c.execute("SELECT COUNT(*) FROM crew").fetchone()[0]
            c.close()
            if admitted:
                break
            time.sleep(0.05)
        assert proc.poll() is None, proc.communicate()
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    assert proc.returncode == 0, err
    assert "Traceback" not in err
    assert out.strip().splitlines()[-1] == (
        "Run r1 is still running; `hermes run resume r1 --wait` picks it up again"
    )
    assert _state(path, "r1") == "running"
