"""An unbounded master loop waits out a human, then finishes the run.

The example playbook routes each phase's tickets to ``needs_human``. The loop
runs with ``max_cycles=None`` (what ``--wait`` asks for) on the local site with
the mock agent, while a second connection on another thread plays the operator.
"""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from engine.db.migrate import apply_migrations, connect
from engine.models import Run
from testkit import fixtures


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    repo = tmp_path / "src"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "README").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, env=env)
    monkeypatch.setenv("HERMES_REPO", str(repo))
    path = str(tmp_path / "queue.db")
    apply_migrations(path)
    yield path
    for suffix in ("", "-shm", "-wal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _operator(db_path, decisions, stop):
    """Resolve each pending reduction in turn with the next decision."""
    from engine import queue

    conn = connect(db_path)
    try:
        for decide in decisions:
            while not stop.is_set():
                row = conn.execute(
                    "SELECT id FROM reductions WHERE review_state='pending'"
                ).fetchone()
                if row:
                    getattr(queue, f"{decide}_reduction")(conn, row[0])
                    break
                time.sleep(0.01)
    finally:
        conn.close()


@pytest.mark.parametrize("last, outcome", [("accept", "done"), ("reject", "failed")])
def test_the_loop_waits_for_the_human_then_finishes(db_path, tmp_path, last, outcome):
    import sites.local  # noqa: F401  (registers "local")
    import testkit  # noqa: F401  (registers "example" and "mock")
    from engine import agent, crew, dispatch, playbook, queue, site

    st, ag, pb = site.load("local"), agent.load("mock"), playbook.load("example")
    host = st.discover_hosts()[0]
    issues = fixtures.write_canned_issues(tmp_path / "issues.json")
    config = {"issue_filters": {"path": str(issues)}, "needs_human": True}

    conn = connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES ('w', 'example', 'local', 'HEAD', ?, 'running', 'work', 0, 0)""",
        (json.dumps(config),),
    )
    conn.commit()
    queue.seed_tickets(conn, Run(id="w", playbook="example", site="local",
                                 base_ref="HEAD", config=config, phase="work",
                                 reductions=[]), pb, st)
    crew.add(conn, st, ag, host=host, base_ref="HEAD")

    stop = threading.Event()
    watchdog = threading.Timer(30, stop.set)  # a hang fails the test, not the suite
    operator = threading.Thread(target=_operator,
                                args=(db_path, ["accept", last], stop))
    watchdog.start()
    operator.start()
    try:
        final = dispatch.master_loop(
            conn, "w", pb, st, ag, "HEAD", hosts=[host],
            max_cycles=None, stop_event=stop, idle_sleep_s=0.01,
        )
    finally:
        stop.set()
        watchdog.cancel()
        operator.join()

    assert final == outcome
    kinds = [r[0] for r in conn.execute(
        "SELECT kind FROM events WHERE run_id='w' ORDER BY id")]
    assert kinds.count("reduction_accepted") == (2 if last == "accept" else 1)
    assert "phase_advanced" in kinds
    conn.close()
