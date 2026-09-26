"""Integration test: one whole committee run against a scripted talking agent.

Real SQLite + migrations, the real ``local`` site, ``crew.add`` and
``dispatch.master_loop`` in a bounded loop with an advancing clock -- the
harness shape from ``tests/integration/test_dexter_run.py:32-108``.

Proves acceptance criteria 2, 3, 4, 5, 6 and 7, plus the deliberately-failed
chair (spec 5.3). The site is the REAL ``local`` site, not a subclass: the
playbook's site guard rejects any name that is neither ``local`` nor ``fan-*``,
so the dexter trick of subclassing ``LocalSite`` under a new name is not
available here.

The talking agent double lives in this file because it has exactly one
consumer. ``MockAgent`` cannot serve: it copies the request payload into
``Result.payload`` (``testkit/mock_agent.py:133``), which can never satisfy a
result schema that differs from the payload schema, and its
``build_invocation`` returns ``["true"]``, so nothing crosses the process
boundary. Stdlib-only: no SSH, no Meta, no real ``claude``.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from engine import config, contracts, crew, dispatch, queue
from engine import playbook as playbook_registry
from engine.db.migrate import apply_migrations, connect
from engine.models import Check, Result
from playbooks.committee import cast, thread, turnblock
from playbooks.committee import playbook as committee
from playbooks.committee import eval as committee_eval


# --- fixtures --------------------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    return tmp_path


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    """A real one-commit git repo wired as HERMES_REPO (for LocalSite.provision)."""
    repo = tmp_path / "src"
    repo.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "README").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, env=env)
    monkeypatch.setenv("HERMES_REPO", str(repo))
    return repo


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "queue.db")
    yield path
    for suffix in ("", "-shm", "-wal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


@pytest.fixture
def conn(db_path):
    apply_migrations(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def local_site():
    """The REAL local site -- the playbook's site guard accepts nothing else."""
    import sites.local  # noqa: F401  (registers "local")
    from engine import site

    return site.load("local")


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    """The one file under review, OUTSIDE HERMES_HOME so tampering is visible."""
    path = tmp_path / "proposal.md"
    path.write_text("# Proposal\n\nMigrate the ingest pipeline to the new scheduler.\n")
    monkeypatch.setenv(committee.ENV_ARTIFACT, str(path))
    monkeypatch.delenv(committee.ENV_MAX_TURNS, raising=False)
    monkeypatch.delenv(committee.ENV_DRIVER, raising=False)
    return path


# --- helpers ---------------------------------------------------------------

CHARGE = "Decide whether to fund the scheduler migration."
EDIT_ACTION = "Add a rollback plan to section 4."
NOOP_ACTION = "no-op: leave the revised copy exactly as it is."

# The opening round with nothing else happening: seven reviewers in seniority
# order, each answered by the owner. t01..t14. The owner cannot close before
# this drains (spec 5.4), so it is the floor of every uncapped run.
OPENING_ROUND = [
    phase
    for index, role in enumerate(cast.SENIORITY)
    for phase in (f"t{2 * index + 1:02d}-{role}", f"t{2 * index + 2:02d}-{cast.OWNER}")
]
LAST_OPENING_OWNER_TURN = OPENING_ROUND[-1]  # "t14-owner"


def _mk_run(conn, run_id):
    """Insert a running committee run parked on the zero-ticket `open` phase."""
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'committee', 'local', 'HEAD', ?, 'running', 'open', 0, 0)""",
        (run_id, json.dumps({"goals": [CHARGE]})),
    )
    conn.commit()


def _run_state(conn, run_id):
    return conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]


def _dispatched_phases(conn, run_id):
    """Every phase that actually ran a worker, in execution order (attempts.id)."""
    rows = conn.execute(
        """SELECT a.phase FROM attempts a JOIN tickets t ON t.id = a.ticket_id
           WHERE t.run_id=? ORDER BY a.id""",
        (run_id,),
    ).fetchall()
    return [row[0] for row in rows]


def _reductions(conn, run_id):
    """[(phase, kind, json)] in insertion order."""
    rows = conn.execute(
        "SELECT phase, kind, json FROM reductions WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [(phase, kind, json.loads(doc)) for phase, kind, doc in rows]


def _reduction_for(conn, run_id, phase):
    for row_phase, _kind, doc in _reductions(conn, run_id):
        if row_phase == phase:
            return doc
    raise AssertionError(f"no reduction recorded for phase {phase!r}")


def _entries(run_id):
    """[(heading, body)] for every '## ' section of thread.md, in file order."""
    sections = []
    heading, body = None, []
    for line in thread.path(run_id).read_text().splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(body).strip()))
            heading, body = line, []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body).strip()))
    return sections


def _turns(run_id):
    return [(h, b) for h, b in _entries(run_id) if h.startswith("## turn ")]


def _heading(number, role):
    persona = cast.CAST[role]
    return f"## turn {number:02d} — {persona['name']}, {persona['title']} ({role})"


def _drive(conn, run_id, pb, site, agent, host, rounds=40):
    """Bounded master_loop drive with an advancing clock. Returns the run state."""
    t = 1000.0
    STEP = 700.0
    for _ in range(rounds):
        dispatch.master_loop(
            conn, run_id, pb, site, agent, "HEAD",
            hosts=[host], now=t, max_cycles=6,
        )
        if _run_state(conn, run_id) in ("done", "failed"):
            break
        t += STEP
    return _run_state(conn, run_id)


def _rule(conn, run_id, pb, site, agent, host, *, accept, phase="decision"):
    """A human rules on the held verdict, then the loop drives on.

    What the Review tab (or `hermes reduction accept|reject`) does while
    `hermes run --wait` keeps the loop alive. The held ticket must be the chair's
    and linked to the decision reduction: a wrong id in `needs_human_ticket_ids`
    routes nothing, silently, and the run would have ended `done` unreviewed.
    ``phase`` is the chair phase whose take was kept (``decision-take2`` after
    a retake): the kept verdict holds its own ticket.
    """
    assert _run_state(conn, run_id) == "running"
    state, reduction_id = conn.execute(
        "SELECT state, reduction_id FROM tickets WHERE id=?", (f"{run_id}/{phase}",)
    ).fetchone()
    assert state == "needs_human"
    assert reduction_id == conn.execute(
        "SELECT id FROM reductions WHERE run_id=? AND phase=?", (run_id, phase)
    ).fetchone()[0]
    (queue.accept_reduction if accept else queue.reject_reduction)(conn, reduction_id)
    return _drive(conn, run_id, pb, site, agent, host)


def _start(conn, run_id, pb, site, agent):
    """Insert the run, seed the zero-ticket `open` phase, admit the host."""
    _mk_run(conn, run_id)
    run = queue.load_run(conn, run_id)
    assert queue.seed_tickets(conn, run, pb, site) == []
    host = site.discover_hosts()[0]
    crew.add(conn, site, agent, host=host, base_ref="HEAD", now=1000.0)
    return host


# --- the scripted talking agent --------------------------------------------

FENCE = "```"
QUIET_REVIEWER = "request_floor: no"
FLOOR_REVIEWER = "request_floor: yes"
OWNER_QUIET = "request_floor: no\ndelegate: no\nclose: no"
OWNER_DELEGATES = (
    "request_floor: no\n"
    "delegate: yes\n"
    f"action: {EDIT_ACTION}\n"
    "close: yes"
)
OWNER_DELEGATES_NOOP = (
    "request_floor: no\n"
    "delegate: yes\n"
    f"action: {NOOP_ACTION}\n"
    "close: yes"
)


# 350 words with a bold span: over every cap (the chair's 300 included), and bold.
# What `violate_phases` returns.
VIOLATION = "**This** " + "word " * 349


def _wrap(prose: str, block: str) -> str:
    """Prose plus one hermes-turn fence -- what a real speaker returns (spec 5.4)."""
    return f"{prose}\n\n{FENCE}{turnblock.FENCE_TAG}\n{block}\n{FENCE}\n"


class ScriptedCommitteeAgent:
    """An agent double that actually talks, and actually edits on an edit turn.

    Every answer is a pure function of ``envelope["payload"]`` -- the model is
    ``DexterLocalSite.recheck_fix`` (``testkit/dexter_doubles.py:178-190``), not
    ``DexterMockAgent``'s mutable per-ticket attempt counter (``:83-93``):

      - ``kind == "decision"`` -> the chair's verdict prose.
      - ``kind == "edit"``     -> the junior IC's line, plus a REAL append to the
        revised copy through the argv the local site execs
        (``engine/transport.py:94-101``), because the master-side re-check in
        ``reduce`` hashes that file off disk, not the result payload. An action
        starting with ``"no-op:"`` is honoured literally: the file is left
        alone, so the re-check fails.
      - ``role == owner``      -> ``owner_block``, fixed at construction.
      - anything else          -> a reviewer turn.

    ``floor_phases`` and ``owner_phases`` are the two hooks keyed on
    ``envelope["phase"]`` rather than the payload: a role's payload is
    byte-identical on every turn that role takes, so a role-keyed floor request
    would re-queue that role on every turn until the cap, and a role-keyed
    delegation would re-delegate on every owner turn. They are still static
    lookups -- no counter, no mutation. ``owner_phases=None`` means every owner
    turn, which is what the quiet default wants.

    ``violate_phases``: those phases answer ``VIOLATION``, so the master
    discards the take and mints a retake; the double never edits on a
    ``-take`` phase, because a retake is report-only.

    The chair's prose deliberately does NOT contain the simulation disclaimer.
    A real chair is asked for one by its completion condition, but a double that
    says it lets the tests pass on the double's own words: the disclaimer the
    product appends (``playbook._SIMULATION``) could be deleted outright and
    every assertion here would still be green.

    Integrity is honoured the way ``DexterMockAgent`` does it: recompute
    ``payload_sha256`` over the received payload, ``contract_fail`` on mismatch.
    """

    name = "scripted_committee"

    def __init__(
        self,
        *,
        owner_block=OWNER_QUIET,
        owner_phases=None,
        fail_roles=(),
        floor_phases=(),
        violate_phases=(),
    ):
        self.owner_block = owner_block
        self.owner_phases = None if owner_phases is None else frozenset(owner_phases)
        self.fail_roles = frozenset(fail_roles)
        self.floor_phases = frozenset(floor_phases)
        self.violate_phases = frozenset(violate_phases)

    # --- Agent protocol ---------------------------------------------------

    def build_invocation(self, envelope: dict, driver) -> list[str]:
        payload = envelope.get("payload") or {}
        action = payload.get("action") or ""
        # A retake phase is report-only: its goal forbids every write, and a
        # double that edited again would fake a "retake modified" error.
        retake = "-take" in str(envelope.get("phase") or "")
        if payload.get("kind") != "edit" or action.startswith("no-op:") or retake:
            return ["true"]
        target = str(
            thread.revised_path(envelope["run_id"], os.environ[committee.ENV_ARTIFACT])
        )
        # The values arrive as positional parameters, never interpolated into
        # the script text, so there is no shell-quoting hazard.
        return [
            "sh", "-c", 'printf "%s\\n" "$2" >> "$1"',
            "sh", target, f"<!-- committee edit: {action} -->",
        ]

    def parse_result(self, raw: str, envelope: dict) -> Result:
        now = time.time()
        payload = envelope.get("payload") or {}

        expected = envelope.get("payload_sha256")
        actual = contracts.payload_sha256(payload)
        if expected is not None and expected != actual:
            return Result(
                outcome="driver_failed",
                termination_reason="contract_fail",
                result_ref=None,
                error_summary=f"payload_sha256 mismatch: expected {expected}, got {actual}",
                started_at=now, ended_at=now, payload={}, evidence_ref=None,
            )

        role = payload.get("role", "")
        if role in self.fail_roles:
            return Result(
                outcome="driver_failed",
                termination_reason="driver_error",
                result_ref=None,
                error_summary=f"scripted driver failure for role {role!r}",
                started_at=now, ended_at=now, payload={}, evidence_ref=None,
            )

        return Result(
            outcome="ok",
            termination_reason="goal_met",
            result_ref=f"result://{envelope.get('ticket_id')}",
            error_summary=None,
            started_at=now, ended_at=now,
            payload={"answer": self._answer(envelope)},
            evidence_ref=None,
        )

    def health_checks(self, host: str, site) -> list[Check]:
        # crew.add raises ValueError unless these pass.
        return [
            Check("agent", True, "scripted committee agent available"),
            Check("auth", True, "scripted committee auth ok"),
        ]

    # --- the script -------------------------------------------------------

    def _answer(self, envelope: dict) -> str:
        payload = envelope.get("payload") or {}
        role = payload.get("role", "")
        kind = payload.get("kind", "")
        if envelope.get("phase") in self.violate_phases:
            if kind in ("decision", "edit"):
                return VIOLATION
            return _wrap(VIOLATION, OWNER_QUIET if role == cast.OWNER else QUIET_REVIEWER)
        if kind == "decision":
            # No disclaimer: that sentence is the PRODUCT's to append. See the
            # class docstring.
            return "Approve with changes: fund the migration once the rollback plan lands."
        if kind == "edit":
            action = payload.get("action") or ""
            if action.startswith("no-op:"):
                return f"I left the revised copy untouched: {action}"
            return f"I applied the delegated change to the revised copy: {action}"
        if role == cast.OWNER:
            speaking = (
                self.owner_phases is None
                or envelope.get("phase") in self.owner_phases
            )
            return _wrap(
                f"{OWNER_PROSE} The fix belongs in `engine/dispatch.py:284`.",
                self.owner_block if speaking else OWNER_QUIET,
            )
        block = (
            FLOOR_REVIEWER if envelope.get("phase") in self.floor_phases
            else QUIET_REVIEWER
        )
        # Two sentences and a backticked path:line, as the rules ask: a rule
        # that wrongly sent two sentences back (multi_sentence is the junior
        # IC's alone) would retake every turn and move every phase list here.
        return _wrap(
            f"{REVIEWER_PROSE} {payload.get('title', role)}. "
            "The risk sits at `engine/dispatch.py:284`.",
            block,
        )


# --- tests -----------------------------------------------------------------

def test_full_conversation_runs_unattended_and_holds_the_verdict_for_a_human(
    home, source_repo, artifact, conn, local_site
):
    """Criteria 2, 3, 4, 5, 6, 8 and 9 over one sixteen-turn conversation.

    The opening round runs in seniority order, the owner answers every reviewer,
    one reviewer (t09-tl) asks for the floor and is granted it once the opening
    round drains, then the chair closes. Nobody delegates an edit, so no revised
    copy is ever created. The verdict is banked, then waits on a human; accepting
    it ends the run `done`.
    """
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(floor_phases={"t09-tl"})
    run_id = "committee-20260918-000001"
    original = thread.digest(artifact)

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"

    # criteria 4 + 5: the exact turn order, one dispatch per phase, no repeats.
    expected_phases = [
        "t01-senior_director", "t02-owner", "t03-manager", "t04-owner",
        "t05-tpm", "t06-owner", "t07-pm", "t08-owner", "t09-tl", "t10-owner",
        "t11-staff_ic", "t12-owner", "t13-data_scientist", "t14-owner",
        "t15-tl", "t16-owner", "decision",
    ]
    phases = _dispatched_phases(conn, run_id)
    assert phases == expected_phases
    assert len(set(phases)) == len(phases)
    assert max(int(p[1:3]) for p in phases if p != "decision") <= 30
    assert phases[-1] == "decision"

    ticket_ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM tickets WHERE run_id=?", (run_id,)
        ).fetchall()
    ]
    assert len(set(ticket_ids)) == len(ticket_ids) == len(expected_phases)

    # criterion 3: one thread entry per turn, in order, each a named persona,
    # with the owner's reply following every reviewer turn.
    roles = [p.split("-", 1)[1] for p in expected_phases if p != "decision"]
    assert [h for h, _ in _turns(run_id)] == [
        _heading(i + 1, role) for i, role in enumerate(roles)
    ]
    for i, role in enumerate(roles[:-1]):
        if role in cast.SENIORITY:
            assert roles[i + 1] == cast.OWNER, f"{role} at turn {i + 1} went unanswered"
    assert all(body and body != thread.NO_TURN for _, body in _turns(run_id))

    # The decision is the chair's, and says out loud that it is a simulation.
    chair = cast.CAST[cast.CHAIR_ROLE]
    decisions = [(h, b) for h, b in _entries(run_id) if h.startswith("## decision")]
    assert len(decisions) == 1
    assert decisions[0][0] == f"## decision — {chair['name']}, {chair['title']}"
    # The PRODUCT's disclaimer, verbatim. The double does not say it, so
    # deleting `parts.append(_SIMULATION)` turns this RED.
    assert committee._SIMULATION in decisions[0][1]
    assert "not an approval, not a sign-off" in decisions[0][1]

    # criterion 6: the original is untouched and no revised copy was ever made --
    # asserted here, and re-checked by the PRODUCT at the decision.
    assert thread.digest(artifact) == original
    assert not thread.revised_path(run_id, str(artifact)).exists()
    assert _reduction_for(conn, run_id, "decision")["artifact_intact"] is True

    # criterion 8: nothing waited on a human mid-run; only the verdict does.
    reductions = _reductions(conn, run_id)
    assert [kind for _, kind, _ in reductions] == ["turn"] * 16 + ["decision"]
    assert all("needs_human_ticket_ids" not in doc for _, _, doc in reductions[:-1])
    assert reductions[-1][2]["needs_human_ticket_ids"] == [f"{run_id}/decision"]
    assert conn.execute(
        "SELECT id FROM tickets WHERE run_id=? AND state='needs_human'", (run_id,)
    ).fetchall() == [(f"{run_id}/decision",)]

    # The floor grant came from t09-tl's block; only a junior IC gets re-checked.
    granted = _reduction_for(conn, run_id, "t09-tl")
    assert granted["request_floor"] is True
    assert granted["verified"] is None
    assert _reduction_for(conn, run_id, "decision")["verdict"].startswith(
        "Approve with changes"
    )

    assert _rule(conn, run_id, pb, local_site, agent, host, accept=True) == "done"


def test_failed_turn_still_gets_a_stub_and_the_run_advances(
    home, source_repo, artifact, conn, local_site, monkeypatch
):
    """Criterion 3, second half: a worker that failed still leaves an entry.

    The opening reviewer's worker returns driver_failed -- terminal on first
    occurrence, no retry, and no finding is written -- so reduce() sees zero
    findings for that phase. The turn still gets the NO_TURN stub, and the
    counter still advances in next_phase, so no phase name repeats and the run
    reaches done.

    And t02 is the NEXT REVIEWER, not the owner. A turn that said nothing is
    answered by nobody: sending the owner to reply to `_(no turn delivered …)_`
    either produces a hallucinated reply or burns the turn.
    """
    monkeypatch.setenv(committee.ENV_MAX_TURNS, "4")
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(fail_roles={"senior_director"})
    run_id = "committee-20260918-000002"

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"
    assert _rule(conn, run_id, pb, local_site, agent, host, accept=True) == "done"

    assert _dispatched_phases(conn, run_id) == [
        "t01-senior_director", "t02-manager", "t03-owner", "t04-tpm", "decision",
    ]
    assert conn.execute(
        "SELECT state FROM tickets WHERE id=?", (f"{run_id}/t01-senior_director",)
    ).fetchone()[0] == "failed"

    turns = _turns(run_id)
    assert [h for h, _ in turns] == [
        _heading(1, "senior_director"), _heading(2, "manager"),
        _heading(3, cast.OWNER), _heading(4, "tpm"),
    ]
    assert turns[0][1] == thread.NO_TURN
    assert turns[1][1] != thread.NO_TURN

    lost = _reduction_for(conn, run_id, "t01-senior_director")
    assert lost["role"] == "senior_director"
    assert lost["turn"] == 1
    assert lost["delivered"] is False


def test_turn_cap_ends_the_conversation_at_the_cap(
    home, source_repo, artifact, conn, local_site, monkeypatch
):
    """Criterion 5: the highest turn number never exceeds max_turns.

    With max_turns=3 the cap falls on a reviewer turn, so that reviewer goes
    unanswered -- the caveat spec 5.3 accepts, because reserving a turn for the
    owner's reply would mint t04 and break the cap.
    """
    monkeypatch.setenv(committee.ENV_MAX_TURNS, "3")
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent()
    run_id = "committee-20260918-000003"

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"
    assert _rule(conn, run_id, pb, local_site, agent, host, accept=True) == "done"

    phases = _dispatched_phases(conn, run_id)
    assert phases == ["t01-senior_director", "t02-owner", "t03-manager", "decision"]
    assert max(int(p[1:3]) for p in phases if p != "decision") == 3
    assert phases[-1] == "decision"
    # Cut off on a reviewer turn: no owner reply follows it.
    assert [h for h, _ in _turns(run_id)][-1] == _heading(3, "manager")
    assert _reduction_for(conn, run_id, "decision")["dropped_delegation"] is None


@pytest.mark.parametrize("accept, ends", [(True, "done"), (False, "failed")])
def test_a_process_that_never_saw_the_meeting_finishes_the_ruling(
    home, source_repo, artifact, conn, local_site, monkeypatch, accept, ends
):
    """The verdict waits on a human for as long as they take. The process that
    ran the meeting may be gone by then -- a closed terminal, Ctrl-C, the board's
    resume -- so the ruling must be read back from the database, not from the
    memory of a playbook instance that held the meeting."""
    monkeypatch.setenv(committee.ENV_MAX_TURNS, "3")
    agent = ScriptedCommitteeAgent()
    run_id = "committee-20260918-000013"

    meeting = committee.CommitteePlaybook()
    host = _start(conn, run_id, meeting, local_site, agent)
    assert _drive(conn, run_id, meeting, local_site, agent, host) == "running"
    assert _rule(
        conn, run_id, committee.CommitteePlaybook(), local_site, agent, host, accept=accept
    ) == ends


def test_a_process_that_never_saw_the_meeting_ends_it_failed_and_says_why(
    home, source_repo, artifact, conn, local_site
):
    """The meeting lives in one process's memory. A fresh process picking it up
    mid-way (`hermes run resume <id> --wait` after Ctrl-C) used to re-mint `t01`
    over a ticket that exists -- UNIQUE constraint failed -- and strand the run
    `running` with nothing driving it."""
    agent = ScriptedCommitteeAgent()
    run_id = "committee-20260918-000014"
    host = _start(conn, run_id, committee.CommitteePlaybook(), local_site, agent)
    dispatch.master_loop(
        conn, run_id, committee.CommitteePlaybook(), local_site, agent, "HEAD",
        hosts=[host], now=1000.0, max_cycles=3,
    )
    assert _run_state(conn, run_id) == "running"
    stopped_at = queue.load_run(conn, run_id).phase
    assert stopped_at not in ("open", "decision", "ruling"), stopped_at

    assert _drive(conn, run_id, committee.CommitteePlaybook(), local_site, agent, host) == "failed"
    lost = conn.execute(
        "SELECT phase, json FROM reductions WHERE run_id=? AND kind='lost'", (run_id,)
    ).fetchall()
    assert [phase for phase, _ in lost] == [stopped_at]
    assert "cannot be resumed" in json.loads(lost[0][1])["error"]


def test_delegated_edit_writes_only_the_revised_copy(
    home, source_repo, artifact, conn, local_site
):
    """Criterion 6: the original stays byte-identical; the revised copy differs.

    The owner's block carries `delegate: yes` AND `close: yes` on one turn, and
    that turn is the last of the opening round, because a close before the round
    drains is ignored (spec 5.4). A delegation outranks close, so the junior
    IC's edit still happens and costs one turn; then `closed` routes straight to
    the decision.
    """
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(
        owner_block=OWNER_DELEGATES, owner_phases={LAST_OPENING_OWNER_TURN}
    )
    run_id = "committee-20260918-000004"
    original = thread.digest(artifact)

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"
    assert _rule(conn, run_id, pb, local_site, agent, host, accept=True) == "done"

    assert _dispatched_phases(conn, run_id) == [
        *OPENING_ROUND, "t15-junior_ic", "decision",
    ]

    revised = thread.revised_path(run_id, str(artifact))
    assert revised.exists()
    assert thread.digest(artifact) == original          # the original is never mutated
    assert thread.digest(revised) != original           # the revised copy carries the edit
    assert artifact.read_text() in revised.read_text()  # a byte copy, then appended to
    assert EDIT_ACTION in revised.read_text()

    owner_turn = _reduction_for(conn, run_id, LAST_OPENING_OWNER_TURN)
    assert owner_turn["role"] == cast.OWNER
    assert owner_turn["delegate"] is True
    assert owner_turn["close"] is True
    assert owner_turn["action"] == EDIT_ACTION

    edit_turn = _reduction_for(conn, run_id, "t15-junior_ic")
    assert edit_turn["role"] == cast.JUNIOR
    assert edit_turn["turn"] == 15
    assert edit_turn["delivered"] is True
    assert edit_turn["verified"] is True                # the master-side re-check

    decision = _reduction_for(conn, run_id, "decision")
    assert decision["rechecks"] == [
        {"turn": 15, "action": EDIT_ACTION, "verified": True}
    ]
    assert decision["dropped_delegation"] is None
    assert _heading(15, cast.JUNIOR) in [h for h, _ in _turns(run_id)]


def test_every_version_is_served_from_a_home_that_moved_away_from_the_master(
    home, source_repo, artifact, conn, local_site, monkeypatch
):
    """The container, in one process: the server's home is not the master's.

    The master records host paths on every reduction. Move the home somewhere
    else and delete the original, and every one of those paths is dead -- which
    is what the control plane in its container sees. Every document version
    must still be listed with a size and served, because both come from the
    fixed ``runs/<id>/doc/`` layout under the SERVER's own home.
    """
    import logging

    from fastapi.testclient import TestClient

    from engine import log
    from server.app import create_app

    # create_app() configures the process-wide "hermes" logger once, onto this
    # test's captured stderr; put it back so later tests' capture still works.
    hermes_logger = logging.getLogger("hermes")
    monkeypatch.setattr(hermes_logger, "handlers", list(hermes_logger.handlers))
    monkeypatch.setattr(hermes_logger, "level", hermes_logger.level)
    monkeypatch.setattr(log, "_configured", log._configured)

    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(
        owner_block=OWNER_DELEGATES, owner_phases={"t02-owner", "t15-owner"}
    )
    run_id = "committee-20260925-000011"
    handed = artifact.read_text()

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"
    assert _rule(conn, run_id, pb, local_site, agent, host, accept=True) == "done"
    assert "t03-junior_ic" in _dispatched_phases(conn, run_id)
    assert "t16-junior_ic" in _dispatched_phases(conn, run_id)

    first_home = Path(os.environ["HERMES_HOME"])
    copy = sqlite3.connect(first_home / "queue.db")
    conn.backup(copy)
    copy.close()
    moved = first_home.parent / "server-home"
    first_home.rename(moved)
    artifact.unlink()
    monkeypatch.setenv("HERMES_HOME", str(moved))

    client = TestClient(create_app())
    document = client.get(f"/api/runs/{run_id}/view").json()["document"]

    assert document["captured"] is True
    assert [step["turn"] for step in document["steps"]] == [3, 16]
    assert all(step["bytes"] is not None for step in document["steps"])
    assert document["final"]["path"] == document["steps"][-1]["path"]
    assert document["final"]["ruling"] == "accepted"
    for version in [document["original"], *document["steps"], document["final"]]:
        response = client.get(
            f"/api/runs/{run_id}/view/artifact", params={"path": version["path"]}
        )
        assert response.status_code == 200, version["path"]
        on_disk = (moved / "runs" / run_id / version["path"]).read_text()
        assert response.json()["text"] == on_disk
        assert len(on_disk.encode()) == version["bytes"]
    doc = moved / "runs" / run_id / "doc"
    assert (doc / "00-original.md").read_text() == handed
    assert (doc / "t03.md").read_text().count(EDIT_ACTION) == 1
    assert (doc / "t16.md").read_text().count(EDIT_ACTION) == 2


def test_failed_recheck_is_named_in_the_decision(
    home, source_repo, artifact, conn, local_site
):
    """Criterion 7: a junior-IC turn whose re-check failed is named explicitly.

    The delegated action starts with "no-op:" and the double honours it
    literally -- it runs `true` instead of appending -- so the revised copy
    still hashes to the original and the master-side re-check in reduce()
    fails. A committee whose edits silently did not apply is worse than one
    that made none, so the failure must reach the decision.

    A human reading that verdict rejects it, and the run ends `failed`: the
    chair's prose is still on record, but nobody signed it off.
    """
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(
        owner_block=OWNER_DELEGATES_NOOP, owner_phases={LAST_OPENING_OWNER_TURN}
    )
    run_id = "committee-20260918-000005"
    original = thread.digest(artifact)

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"
    assert _rule(conn, run_id, pb, local_site, agent, host, accept=False) == "failed"
    assert conn.execute(
        "SELECT t.state, r.review_state FROM tickets t JOIN reductions r"
        " ON r.id = t.reduction_id WHERE t.id=?", (f"{run_id}/decision",)
    ).fetchone() == ("failed", "rejected")

    assert _dispatched_phases(conn, run_id) == [
        *OPENING_ROUND, "t15-junior_ic", "decision",
    ]

    revised = thread.revised_path(run_id, str(artifact))
    assert revised.exists()                      # seed copied it
    assert thread.digest(revised) == original    # ... and the worker changed nothing
    assert thread.digest(artifact) == original

    edit_turn = _reduction_for(conn, run_id, "t15-junior_ic")
    assert edit_turn["delivered"] is True
    assert edit_turn["verified"] is False

    decision = _reduction_for(conn, run_id, "decision")
    assert decision["rechecks"] == [
        {"turn": 15, "action": NOOP_ACTION, "verified": False}
    ]
    # Named in the transcript itself, not buried in the reduction json -- and
    # named as a FAILURE. Without the verdict, an unconditional "APPLIED" reads
    # exactly like a successful edit to the human who reads this file.
    body = [b for h, b in _entries(run_id) if h.startswith("## decision")][0]
    assert NOOP_ACTION in body
    assert "DID NOT APPLY" in body
    assert "APPLIED —" not in body


def test_the_cap_drops_a_delegation_and_the_decision_says_so(
    home, source_repo, artifact, conn, local_site, monkeypatch
):
    """The other half of criterion 5: a delegation the cap cuts off is recorded.

    The owner delegates on t02 with the cap at 2, so there is no t03 to spend on
    the edit. `_decision` must move the pending delegation to
    `dropped_delegation` rather than dropping it on the floor: an edit the owner
    asked for and never got is a fact about this committee's output.
    """
    monkeypatch.setenv(committee.ENV_MAX_TURNS, "2")
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(owner_block=OWNER_DELEGATES)
    run_id = "committee-20260918-000007"
    original = thread.digest(artifact)

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"
    assert _rule(conn, run_id, pb, local_site, agent, host, accept=True) == "done"

    # No junior-IC turn: the cap fell before one could be minted.
    assert _dispatched_phases(conn, run_id) == [
        "t01-senior_director", "t02-owner", "decision",
    ]
    assert not thread.revised_path(run_id, str(artifact)).exists()
    assert thread.digest(artifact) == original

    owner_turn = _reduction_for(conn, run_id, "t02-owner")
    assert owner_turn["delegate"] is True
    assert owner_turn["action"] == EDIT_ACTION

    decision = _reduction_for(conn, run_id, "decision")
    assert decision["dropped_delegation"] == EDIT_ACTION
    assert decision["rechecks"] == []

    # And a human reading only thread.md still learns the edit never happened.
    body = [b for h, b in _entries(run_id) if h.startswith("## decision")][0]
    assert "dropped_delegation" in body
    assert EDIT_ACTION in body
    assert "no edit was made" in body


def test_failed_chair_turn_fails_the_run(
    home, source_repo, artifact, conn, local_site, monkeypatch
):
    """Spec 5.3: no decision means the committee did not finish.

    A chair turn with no result writes no finding, so reduce("decision") sets no
    verdict, is_done is False, and engine/dispatch.py:295 fails the run. This is
    deliberate -- fabricating a verdict would be worse. The decision reduction
    is still recorded, so the transcript stands.
    """
    monkeypatch.setenv(committee.ENV_MAX_TURNS, "1")
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(fail_roles={cast.CHAIR})
    run_id = "committee-20260918-000006"

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "failed"

    assert _dispatched_phases(conn, run_id) == ["t01-senior_director", "decision"]
    assert conn.execute(
        "SELECT state FROM tickets WHERE id=?", (f"{run_id}/decision",)
    ).fetchone()[0] == "failed"

    decision = _reduction_for(conn, run_id, "decision")
    assert decision["delivered"] is False
    assert decision["verdict"] == ""
    # Nothing to rule on, so nothing waits in the review queue.
    assert decision["needs_human_ticket_ids"] == []

    # The transcript still stands: turn 01 was delivered.
    assert [h for h, _ in _turns(run_id)] == [_heading(1, "senior_director")]
    assert _turns(run_id)[0][1] != thread.NO_TURN


# --- retakes (voice T12) -------------------------------------------------------

def test_a_violating_turn_is_retaken_and_only_the_kept_take_reaches_the_thread(
    home, source_repo, artifact, conn, local_site
):
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(violate_phases={"t02-owner", "t02-owner-take2"})
    run_id = "committee-retake"
    host = _start(conn, run_id, pb, local_site, agent)

    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"

    phases = _dispatched_phases(conn, run_id)
    assert phases[:4] == ["t01-senior_director", "t02-owner", "t02-owner-take2", "t02-owner-take3"]
    # retakes cost no turns: the non-take phases are the quiet run's, exactly
    assert [p for p in phases if "-take" not in p] == OPENING_ROUND + ["decision"]
    takes = [(phase, doc) for phase, kind, doc in _reductions(conn, run_id) if kind == "take"]
    assert [phase for phase, _ in takes] == ["t02-owner", "t02-owner-take2"]
    assert [doc["take"] for _, doc in takes] == [1, 2]
    (payload,) = conn.execute(
        "SELECT payload_json FROM tickets WHERE id=?", (f"{run_id}/t02-owner-take2",)
    ).fetchone()
    assert "Retake 2 of 3" in json.loads(payload)["goal"]
    kept = _reduction_for(conn, run_id, "t02-owner-take3")
    assert (kept["take"], kept["takes"], kept["violations"]) == (3, 3, [])
    assert [b for h, b in _turns(run_id) if h == _heading(2, cast.OWNER)] == [kept["body"]]


def test_a_junior_retake_reports_without_editing_again(
    home, source_repo, artifact, conn, local_site
):
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(
        owner_block=OWNER_DELEGATES, owner_phases={"t02-owner"},
        violate_phases={"t03-junior_ic"},
    )
    run_id = "committee-junior-retake"
    host = _start(conn, run_id, pb, local_site, agent)

    _drive(conn, run_id, pb, local_site, agent, host)

    assert _dispatched_phases(conn, run_id)[2:4] == ["t03-junior_ic", "t03-junior_ic-take2"]
    kept = _reduction_for(conn, run_id, "t03-junior_ic-take2")
    assert kept["verified"] is True and kept["error"] is None
    revised = thread.revised_path(run_id, str(artifact)).read_text()
    assert revised.count(f"<!-- committee edit: {EDIT_ACTION} -->") == 1


def test_a_retaken_verdict_is_held_under_its_own_phase_and_an_accept_ends_it_done(
    home, source_repo, artifact, conn, local_site
):
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(violate_phases={"decision"})
    run_id = "committee-chair-retake"
    host = _start(conn, run_id, pb, local_site, agent)

    assert _drive(conn, run_id, pb, local_site, agent, host) == "running"
    assert _dispatched_phases(conn, run_id)[-2:] == ["decision", "decision-take2"]
    assert _rule(conn, run_id, pb, local_site, agent, host,
                 accept=True, phase="decision-take2") == "done"
    assert len([h for h, _ in _entries(run_id) if h.startswith("## decision")]) == 1


# --- committee-eval: the scripted judge and T22-T25 -------------------------


def test_eval_scores_scripted_run(eval_home, source_repo, artifact, local_site, monkeypatch):
    """T22: a scripted committee run, then a scripted judge -> the eval run is done.

    All six dimensions score, each on at least one verified evidence item, and
    the ledger gains exactly one line. The target (its rows and its files) is
    exactly as it was, except for the one file Q5 allows: runs/<target>/eval.json.
    """
    conn = eval_home
    target = _committee_target(conn, local_site, "committee-20260925-000022", monkeypatch)
    home = committee_eval.eval_home()
    run_dir = Path(home) / "runs" / target
    rows, files = _target_rows(conn, target), _tree(run_dir)
    assert {"thread.md", "revised/proposal.md", "doc/00-original.md", "doc/t03.md"} <= set(files)

    eval_run = _eval(conn, local_site, ScriptedJudgeAgent(), target)

    assert _run_state(conn, eval_run) == "done"
    assert _dispatched_phases(conn, eval_run) == ["judge"]
    path = committee_eval.eval_json_path(home, home, target)
    assert path == run_dir / "eval.json"
    body = json.loads(path.read_text())
    reductions = _reductions(conn, eval_run)
    assert [(phase, kind) for phase, kind, _ in reductions] == [
        ("measure", "eval_target"), ("judge", "eval"),
    ]
    assert reductions[-1][2] == body
    assert (body["schema"], body["eval_run"]) == (1, eval_run)
    assert (body["target"]["home"], body["target"]["run"]) == (home, target)
    assert body["judge"]["status"] == "ok", body["judge"]

    dims = body["dimensions"]
    assert set(dims) == set(committee_eval.DIMENSIONS)
    for dim, doc in dims.items():
        assert isinstance(doc["score"], int) and 1 <= doc["score"] <= 5, (dim, doc)
        assert any(item["verified"] is True for item in doc["evidence"]), (dim, doc)
    for dim in committee_eval.DETERMINISTIC_DIMS:
        assert dims[dim]["scorer"] == "deterministic"
    for dim, cited in JUDGE_EVIDENCE.items():
        assert dims[dim]["scorer"] == "judge"
        [item] = dims[dim]["evidence"]
        assert {key: item[key] for key in cited} == cited, (dim, item)
        assert item["verified"] is True and isinstance(item["line"], int), (dim, item)
    assert dims["verdict_grounded"]["score"] == JUDGE_SCORES["verdict_grounded"]
    assert dims["edits_address_concerns"]["score"] == JUDGE_SCORES["edits_address_concerns"]
    # G7: concern_coverage is the judge's 5, capped by this run's own record.
    # The cap of 4 left t04 (manager) unanswered, and five reviewers never spoke.
    metrics = body["metrics"]
    assert metrics["seats"]["unheard"] == ["tpm", "pm", "tl", "staff_ic", "data_scientist"]
    assert metrics["unanswered_reviewer_turns"] == [4]
    assert dims["concern_coverage"]["score"] == committee_eval.concern_cap(
        JUDGE_SCORES["concern_coverage"], metrics
    ) == 3

    lines = committee_eval.ledger_path(home).read_text().splitlines()
    assert len(lines) == 1
    line = json.loads(lines[0])
    assert (line["source"], line["eval_run"], line["judge_status"]) == ("eval", eval_run, "ok")

    assert _target_rows(conn, target) == rows
    after = _tree(run_dir)
    assert after.pop("eval.json")[0] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert after == files


def test_eval_failed_judge(eval_home, source_repo, artifact, local_site, monkeypatch):
    """T23: a judge whose worker fails ends the eval run failed, and still writes.

    The deterministic half survives: eval.json and one ledger line are written,
    status is failed and the judge dimensions are null. The target is left
    waiting on its ruling on purpose. Evaluability never depends on the ruling
    (Q1/R1), and the target must still be waiting after the eval, untouched.
    """
    conn = eval_home
    target = _committee_target(
        conn, local_site, "committee-20260925-000023", monkeypatch, rule=False
    )
    home = committee_eval.eval_home()
    run_dir = Path(home) / "runs" / target
    rows, files = _target_rows(conn, target), _tree(run_dir)

    eval_run = _eval(conn, local_site, ScriptedJudgeAgent(fail=True), target)

    assert _run_state(conn, eval_run) == "failed"
    assert conn.execute(
        "SELECT state FROM tickets WHERE id=?", (f"{eval_run}/judge",)
    ).fetchone()[0] == "failed"
    body = json.loads(committee_eval.eval_json_path(home, home, target).read_text())
    assert body["judge"]["status"] == "failed"
    dims = body["dimensions"]
    assert all(dims[dim]["score"] is None for dim in committee_eval.JUDGE_DIMS)
    # Each judge dimension says why it is null: the failure, not a parse error.
    assert body["judge"]["error"] == "the judge returned no result (driver_failed or timeout)"
    assert all(dims[dim]["error"] == body["judge"]["error"] for dim in committee_eval.JUDGE_DIMS)
    assert all(isinstance(dims[dim]["score"], int) for dim in committee_eval.DETERMINISTIC_DIMS)
    lines = committee_eval.ledger_path(home).read_text().splitlines()
    assert [json.loads(line)["judge_status"] for line in lines] == ["failed"]

    assert _run_state(conn, target) == "running"
    assert _target_rows(conn, target) == rows
    after = _tree(run_dir)
    after.pop("eval.json")
    assert after == files


def test_eval_detects_source_write(
    eval_home, source_repo, artifact, local_site, monkeypatch, tmp_path
):
    """T24: a judge that writes what it was told only to read is caught.

    It writes into the SOURCE (the target's thread.md) and into its own inputs/
    copy (entries.json, the file its quotes are verified against). It deletes a
    source (the revised copy) and a copy (metrics.json). It swaps a copy for a
    symlink to identical bytes, and it adds a file under the target's run
    directory, which measure never copied. Each time judge.reduce's re-hash
    flags target_changed_during_eval, nulls the judge scores with the failure
    as their error, never reads the answer, and fails the eval run.
    """
    conn = eval_home
    target = _committee_target(conn, local_site, "committee-20260925-000024", monkeypatch)
    home = committee_eval.eval_home()
    run_dir = Path(home) / "runs" / target

    def copy(n, name):
        # _eval names its runs <target>-eval-<n>, so a run's inputs/ can be aimed at
        # before that run exists.
        return Path(home) / "runs" / f"{target}-eval-{n}" / "inputs" / name

    outside = tmp_path / "identical-entries.json"
    cases = [  # (the judge's shell script and its args, the path the flag must name)
        (None, run_dir / "thread.md"),
        (None, copy(2, "entries.json")),
        (('rm -f "$1"', run_dir / "revised" / "proposal.md"), run_dir / "revised" / "proposal.md"),
        (('rm -f "$1"', copy(4, "metrics.json")), copy(4, "metrics.json")),
        (('cp "$1" "$2" && rm -f "$1" && ln -s "$2" "$1"', copy(5, "entries.json"), outside),
         copy(5, "entries.json")),
        (('printf x > "$1"', run_dir / "doc" / "t99.md"), run_dir),
    ]
    for n, (script, flagged) in enumerate(cases, 1):
        agent = (ScriptedJudgeAgent(write_to=str(flagged)) if script is None
                 else ScriptedJudgeAgent(script=(script[0], *map(str, script[1:]))))
        eval_run = _eval(conn, local_site, agent, target)
        assert eval_run == f"{target}-eval-{n}"
        if script is None:
            assert flagged.read_text().endswith(PLANTED + "\n")  # the double really wrote
        assert _run_state(conn, eval_run) == "failed"
        (_, _, measured), (_, _, body) = _reductions(conn, eval_run)
        changed = [f for f in body["flags"] if f["id"] == "target_changed_during_eval"]
        assert len(changed) == 1, body["flags"]
        assert (changed[0]["turn"], changed[0]["line"], changed[0]["quote"]) == (None, None, "")
        assert os.path.realpath(flagged) in {os.path.realpath(p) for p in changed[0]["paths"]}, n
        assert body["judge"]["status"] == "failed"
        assert body["judge"]["evidence_rejected"] == 0
        for dim in committee_eval.JUDGE_DIMS:  # never parsed, so never a planted quote read
            doc = body["dimensions"][dim]
            assert (doc["score"], doc["evidence"], doc["error"]) == (
                None, [], body["judge"]["error"]), (n, dim)
        # Not a measure flag (D7): the deterministic block never carries it.
        assert all(f["id"] != "target_changed_during_eval" for f in measured["flags"])

    assert json.loads(committee_eval.eval_json_path(home, home, target).read_text()) == body
    lines = committee_eval.ledger_path(home).read_text().splitlines()
    assert [json.loads(line)["judge_status"] for line in lines] == ["failed"] * len(cases)


def test_eval_foreign_home_read_only(
    eval_home, source_repo, artifact, local_site, monkeypatch, tmp_path
):
    """T25: a foreign source home is read and never written.

    The committee run lives under HERMES_HOME=A. The eval runs under B with
    HERMES_COMMITTEE_EVAL_HOME=A. The result lands in B's evals/, named for A's
    realpath. Afterwards A (its queue.db and every file under it) is
    byte-identical, and no file has been added. queue.db-shm is exempt from the
    byte check only, because a mode=ro reader of a WAL database updates its
    read marks there.
    """
    target = _committee_target(eval_home, local_site, "committee-20260925-000025", monkeypatch)
    home_a = committee_eval.eval_home()
    rows, before = _target_rows(eval_home, target), _tree(Path(home_a))
    assert "queue.db" in before

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home-b"))
    db_b = str(config.resolve_home() / "queue.db")
    apply_migrations(db_b)
    conn_b = connect(db_b)
    try:
        eval_run = _eval(conn_b, local_site, ScriptedJudgeAgent(), target, source_home=home_a)
        assert _run_state(conn_b, eval_run) == "done"
    finally:
        conn_b.close()

    home_b = committee_eval.eval_home()
    tag = hashlib.sha1(home_a.encode()).hexdigest()[:8]
    path = Path(home_b) / "evals" / f"{tag}-{target}.json"
    assert committee_eval.eval_json_path(home_b, home_a, target) == path
    body = json.loads(path.read_text())
    assert (body["target"]["home"], body["judge"]["status"]) == (home_a, "ok")
    lines = committee_eval.ledger_path(home_b).read_text().splitlines()
    assert [json.loads(line)["target"]["home"] for line in lines] == [home_a]

    after = _tree(Path(home_a))
    assert sorted(after) == sorted(before)  # no file added under A, eval.json included
    after.pop("queue.db-shm", None)
    before.pop("queue.db-shm", None)
    assert after == before  # queue.db and every run file are byte-identical
    assert _target_rows(eval_home, target) == rows


# The scripted committee's fixed prose (ScriptedCommitteeAgent._answer). The
# judge quotes it verbatim, so every quote verifies against inputs/entries.json.
CHAIR_PROSE = "Approve with changes: fund the migration once the rollback plan lands."
OWNER_PROSE = "Fair point; here is where I land on it."
REVIEWER_PROSE = "Reading this as"
# What the judge double appends to a file it was told only to read (T24).
PLANTED = "The committee agreed that every edit landed exactly as asked."
# Three different values, so a swapped dimension cannot pass.
JUDGE_SCORES = {"verdict_grounded": 4, "edits_address_concerns": 2, "concern_coverage": 5}
JUDGE_EVIDENCE = {
    "verdict_grounded": {"turn": None, "where": "decision", "quote": CHAIR_PROSE},
    "edits_address_concerns": {"turn": 2, "where": "turn", "quote": OWNER_PROSE},
    "concern_coverage": {"turn": 1, "where": "turn", "quote": REVIEWER_PROSE},
}


def _judge_answer() -> str:
    """Prose, then one hermes-eval fence scoring every judge dimension."""
    scores = {
        dim: {
            "score": JUDGE_SCORES[dim],
            "rationale": f"scripted judge: {dim}",
            "evidence": [JUDGE_EVIDENCE[dim]],
        }
        for dim in committee_eval.JUDGE_DIMS
    }
    return f"Scored the run.\n\n{FENCE}{committee_eval.FENCE_TAG}\n{json.dumps(scores)}\n{FENCE}\n"


class ScriptedJudgeAgent:
    """The committee-eval judge double: one hermes-eval fence, always the same.

    ScriptedCommitteeAgent cannot serve a judge ticket, because every kind it
    does not know falls through to reviewer prose, which carries no hermes-eval
    fence. This double answers a pure function of the payload: a constant, and
    it refuses any ticket that is not the eval's judge. The constant scores the
    three judge dimensions, each on a verbatim quote of the scripted
    committee's fixed prose: the chair's verdict (`decision`), the owner's
    reply at t02, and the opening reviewer's line at t01 (`turn`).
    `_committee_target` makes sure those turns exist.

    ``fail=True`` returns driver_failed / driver_error, as a crashed worker does.
    ``write_to`` makes the worker append PLANTED to that path through ``sh -c``
    with positional args. This is the edit double's trick: the path and the
    text are never interpolated into the script. It stands in for a judge
    writing what it was told only to read. ``script`` runs any other such
    ``sh -c`` script (a delete, a symlink swap) the same way. Integrity is honoured as in
    ScriptedCommitteeAgent: a ``payload_sha256`` mismatch is a contract_fail.
    """

    name = "scripted_judge"

    def __init__(self, *, fail: bool = False, write_to: str | None = None,
                 script: tuple[str, ...] | None = None):
        self.fail = fail
        self.write_to = write_to
        self.script = script  # (sh script, *positional args): a delete or a swap

    def build_invocation(self, envelope: dict, driver) -> list[str]:
        if self.script is not None:
            return ["sh", "-c", self.script[0], "sh", *self.script[1:]]
        if self.write_to is None:
            return ["true"]
        return ["sh", "-c", 'printf "%s\\n" "$2" >> "$1"', "sh", self.write_to, PLANTED]

    def parse_result(self, raw: str, envelope: dict) -> Result:
        now = time.time()
        payload = envelope.get("payload") or {}

        def failed(reason: str, summary: str) -> Result:
            return Result(
                outcome="driver_failed", termination_reason=reason, result_ref=None,
                error_summary=summary, started_at=now, ended_at=now, payload={},
                evidence_ref=None,
            )

        expected = envelope.get("payload_sha256")
        actual = contracts.payload_sha256(payload)
        if expected is not None and expected != actual:
            return failed("contract_fail", f"payload_sha256 mismatch: expected {expected}, got {actual}")
        if payload.get("kind") != "judge":
            return failed("contract_fail", f"scripted judge got a {payload.get('kind')!r} ticket")
        if self.fail:
            return failed("driver_error", "scripted judge failure")
        return Result(
            outcome="ok",
            termination_reason="goal_met",
            result_ref=f"result://{envelope.get('ticket_id')}",
            error_summary=None,
            started_at=now, ended_at=now,
            payload={"answer": _judge_answer()},
            evidence_ref=None,
        )

    def health_checks(self, host: str, site) -> list[Check]:
        # crew.add and every heartbeat sweep re-probe these under this agent.
        return [
            Check("agent", True, "scripted judge agent available"),
            Check("auth", True, "scripted judge auth ok"),
        ]


@pytest.fixture
def eval_home(tmp_path, monkeypatch):
    """A HERMES_HOME whose queue.db lives inside it, as a real home's does.

    The eval reads its source as ``<home>/queue.db`` (mode=ro). The module's
    ``db_path``/``conn`` put queue.db beside the home, not in it, so the eval
    would find nothing there. The fixture yields the connection. The scripted
    committee run and the eval run share it, just as they share
    ~/.hermes/queue.db live.
    """
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home-a"))
    db = str(config.resolve_home() / "queue.db")
    apply_migrations(db)
    connection = connect(db)
    yield connection
    connection.close()


def _committee_target(conn, site, run_id, monkeypatch, *, rule=True):
    """Run the four-turn scripted committee that every eval test scores; return its id.

    The turns are t01 senior_director, t02 owner and t03 junior_ic. The owner
    delegates at t02, so t03 makes a real edit and revised/ and doc/ exist.
    Then come t04 manager and the chair, at the cap of 4. The cap leaves t04
    unanswered and five reviewers unheard, which gives the concern_coverage cap
    something to bite on. ``rule=False`` leaves the verdict waiting on a human.
    The run then stays ``running``, and it is evaluable all the same (spec R1).
    """
    monkeypatch.setenv(committee.ENV_MAX_TURNS, "4")
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(owner_block=OWNER_DELEGATES, owner_phases={"t02-owner"})
    host = _start(conn, run_id, pb, site, agent)
    assert _drive(conn, run_id, pb, site, agent, host) == "running"
    assert _dispatched_phases(conn, run_id) == [
        "t01-senior_director", "t02-owner", "t03-junior_ic", "t04-manager", "decision",
    ]
    if rule:
        assert _rule(conn, run_id, pb, site, agent, host, accept=True) == "done"
    return run_id


def _eval(conn, site, agent, target_run, *, source_home=None):
    """Start one committee-eval run of ``target_run`` on ``conn``, drive it, return its id.

    This is what `eval_cli run` does through `engine.cli`, minus the agent
    registry. The target rides in the environment, where measure.reduce reads
    it once. The run is inserted at phase 0 and seeded (measure seeds nothing).
    The host is re-admitted under this agent, and `_drive` runs the eval to its
    end. The id is ``<target>-eval-<n>``, where n counts this connection's
    committee-eval runs, so a test can aim at a path inside a run before it
    exists.
    """
    pb = playbook_registry.load("committee-eval")
    count = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE playbook='committee-eval'"
    ).fetchone()[0]
    eval_run = f"{target_run}-eval-{count + 1}"
    now = time.time()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(committee_eval.ENV_RUN, target_run)
        if source_home is None:
            mp.delenv(committee_eval.ENV_HOME, raising=False)
        else:
            mp.setenv(committee_eval.ENV_HOME, source_home)
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'committee-eval', ?, 'HEAD', '{}', 'running', ?, ?, ?)""",
            (eval_run, site.name, pb.phases[0], now, now),
        )
        conn.commit()
        assert queue.seed_tickets(conn, queue.load_run(conn, eval_run), pb, site) == []
        host = site.discover_hosts()[0]
        crew.add(conn, site, agent, host=host, base_ref="HEAD", now=1000.0)
        _drive(conn, eval_run, pb, site, agent, host)
    return eval_run


def _target_rows(conn, run_id):
    """Every row the target owns, in id order (runs, tickets, attempts, events, reductions)."""
    queries = {
        "runs": "SELECT * FROM runs WHERE id=?1",
        "tickets": "SELECT * FROM tickets WHERE run_id=?1 ORDER BY id",
        "attempts": """SELECT a.* FROM attempts a JOIN tickets t ON t.id = a.ticket_id
                       WHERE t.run_id=?1 ORDER BY a.id""",
        "events": """SELECT * FROM events WHERE run_id=?1
                     OR ticket_id IN (SELECT id FROM tickets WHERE run_id=?1) ORDER BY id""",
        "reductions": "SELECT * FROM reductions WHERE run_id=?1 ORDER BY id",
    }
    return {name: conn.execute(sql, (run_id,)).fetchall() for name, sql in queries.items()}


def _tree(root: Path) -> dict[str, tuple]:
    """{relative path: (sha256, st_mode, st_mtime_ns, st_ino)} of every entry under ``root``.

    Directories and symlinks too (sha256 None), from lstat: an eval that adds an
    empty directory, or rewrites a file with the same bytes, still shows.
    """
    tree = {}
    for p in sorted(root.rglob("*")):
        info = p.lstat()
        digest = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None
        tree[str(p.relative_to(root))] = (digest, info.st_mode, info.st_mtime_ns, info.st_ino)
    return tree
