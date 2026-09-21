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

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from engine import contracts, crew, dispatch, queue
from engine.db.migrate import apply_migrations, connect
from engine.models import Check, Result
from playbooks.committee import cast, thread, turnblock
from playbooks.committee import playbook as committee


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
    ):
        self.owner_block = owner_block
        self.owner_phases = None if owner_phases is None else frozenset(owner_phases)
        self.fail_roles = frozenset(fail_roles)
        self.floor_phases = frozenset(floor_phases)

    # --- Agent protocol ---------------------------------------------------

    def build_invocation(self, envelope: dict, driver) -> list[str]:
        payload = envelope.get("payload") or {}
        action = payload.get("action") or ""
        if payload.get("kind") != "edit" or action.startswith("no-op:"):
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
                "Fair point; here is where I land on it.",
                self.owner_block if speaking else OWNER_QUIET,
            )
        block = (
            FLOOR_REVIEWER if envelope.get("phase") in self.floor_phases
            else QUIET_REVIEWER
        )
        return _wrap(f"Reading this as {payload.get('title', role)}.", block)


# --- tests -----------------------------------------------------------------

def test_full_conversation_reaches_done_with_no_human(
    home, source_repo, artifact, conn, local_site
):
    """Criteria 2, 3, 4, 5, 6, 8 and 9 over one sixteen-turn conversation.

    The opening round runs in seniority order, the owner answers every reviewer,
    one reviewer (t09-tl) asks for the floor and is granted it once the opening
    round drains, then the chair closes. Nobody delegates an edit, so no revised
    copy is ever created.
    """
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(floor_phases={"t09-tl"})
    run_id = "committee-20260918-000001"
    original = thread.digest(artifact)

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "done"

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

    # criterion 6: the original is untouched and no revised copy was ever made.
    assert thread.digest(artifact) == original
    assert not thread.revised_path(run_id, str(artifact)).exists()

    # criterion 8: nothing ever waited on a human.
    reductions = _reductions(conn, run_id)
    assert [kind for _, kind, _ in reductions] == ["turn"] * 16 + ["decision"]
    assert all("needs_human_ticket_ids" not in doc for _, _, doc in reductions)
    assert conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE run_id=? AND state='needs_human'",
        (run_id,),
    ).fetchone()[0] == 0

    # The floor grant came from t09-tl's block; only a junior IC gets re-checked.
    granted = _reduction_for(conn, run_id, "t09-tl")
    assert granted["request_floor"] is True
    assert granted["verified"] is None
    assert _reduction_for(conn, run_id, "decision")["verdict"].startswith(
        "Approve with changes"
    )


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
    assert _drive(conn, run_id, pb, local_site, agent, host) == "done"

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
    assert _drive(conn, run_id, pb, local_site, agent, host) == "done"

    phases = _dispatched_phases(conn, run_id)
    assert phases == ["t01-senior_director", "t02-owner", "t03-manager", "decision"]
    assert max(int(p[1:3]) for p in phases if p != "decision") == 3
    assert phases[-1] == "decision"
    # Cut off on a reviewer turn: no owner reply follows it.
    assert [h for h, _ in _turns(run_id)][-1] == _heading(3, "manager")
    assert _reduction_for(conn, run_id, "decision")["dropped_delegation"] is None


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
    assert _drive(conn, run_id, pb, local_site, agent, host) == "done"

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


def test_failed_recheck_is_named_in_the_decision(
    home, source_repo, artifact, conn, local_site
):
    """Criterion 7: a junior-IC turn whose re-check failed is named explicitly.

    The delegated action starts with "no-op:" and the double honours it
    literally -- it runs `true` instead of appending -- so the revised copy
    still hashes to the original and the master-side re-check in reduce()
    fails. A committee whose edits silently did not apply is worse than one
    that made none, so the failure must reach the decision.
    """
    pb = committee.CommitteePlaybook()
    agent = ScriptedCommitteeAgent(
        owner_block=OWNER_DELEGATES_NOOP, owner_phases={LAST_OPENING_OWNER_TURN}
    )
    run_id = "committee-20260918-000005"
    original = thread.digest(artifact)

    host = _start(conn, run_id, pb, local_site, agent)
    assert _drive(conn, run_id, pb, local_site, agent, host) == "done"

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
    assert _drive(conn, run_id, pb, local_site, agent, host) == "done"

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

    # The transcript still stands: turn 01 was delivered.
    assert [h for h, _ in _turns(run_id)] == [_heading(1, "senior_director")]
    assert _turns(run_id)[0][1] != thread.NO_TURN
