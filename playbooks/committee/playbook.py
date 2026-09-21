"""CommitteePlaybook — a simulated review committee over a single artifact.

Nine personas read one file and argue about it in one thread. The engine sees two
static phases (``open``, ``decision``); every turn between them is a phase minted
at runtime as ``t{NN:02d}-{role}`` — one ticket, one speaker, strictly serial.

This module is the state machine. ``next_phase`` decides who speaks next and
``is_done`` decides when the meeting is over. Everything they need lives in a
per-run dict on the instance (``_state``), because ``run.config`` is read-only and
``run.reductions`` reaches only one phase back. That is safe: a run is never
resumed, and ``seed``/``reduce``/``next_phase``/``is_done`` all run in the master
process against the one registry singleton.

Ordering is load-bearing and was verified by simulation rather than by reading. A
pending delegation outranks ``close`` — an edit the owner asked for still happens,
and costs one turn — and the turn cap outranks both, so ``t31`` can never be minted
under ``max_turns=30``. A delegation the cap does drop is recorded as
``dropped_delegation`` rather than lost.

Stdlib-only.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from engine import playbook as _playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket
from playbooks.committee import cast, thread, turnblock

if TYPE_CHECKING:  # avoid import cycle
    from engine.site import Site

_CACHE_MAX = 16

ENV_ARTIFACT = "HERMES_COMMITTEE_ARTIFACT"
ENV_MAX_TURNS = "HERMES_COMMITTEE_MAX_TURNS"
ENV_DRIVER = "HERMES_COMMITTEE_DRIVER"

DEFAULT_MAX_TURNS = 30
DEFAULT_CHARGE = "Decide whether to approve this proposal."

# A turn that was delivered but carried only its hermes-turn block.
_SIGNALS_ONLY = "_(the speaker sent signals only, no prose)_"


def _apply_block(s: dict, role: str, block: dict) -> None:
    """The gates of spec 5.4, applied to one speaker's parsed hermes-turn block.

    Enforced, not advisory — and there is exactly ONE copy of them. Task 7's
    ``reduce`` calls this after parsing an answer, and the state-machine tests
    drive it through ``_drive``. A second transcription in the tests would let
    the product's gates rot while every test layer stayed green.
    """
    if block.get("request_floor") and role not in (cast.OWNER, cast.JUNIOR, cast.CHAIR):
        # `opening` as well as `queue`: a delegated turn mints without popping,
        # so a role can still be waiting in the opening round.
        if role not in s["queue"] and role not in s["opening"]:
            s["queue"].append(role)
    if role == cast.OWNER:
        if block.get("close"):
            s["closed"] = True
        if block.get("delegate") and block.get("action"):
            s["delegation"] = block["action"]


def _latest_answer(findings: list[Finding] | None) -> str:
    """The last non-empty ``answer`` in a settled phase's findings.

    One ticket per phase means there is normally exactly one, but findings are
    append-only and arrive id-ascending (``ORDER BY f.id``,
    ``engine/queue.py:883``), so the last write wins -- the same fold
    ``playbooks/dexter/playbook.py:240-245`` does per ticket id. A turn whose
    worker failed writes no finding at all, and folds to ``""``.
    """
    answer = ""
    for finding in findings or ():
        value = (finding.json or {}).get("answer")
        if isinstance(value, str) and value.strip():
            answer = value
    return answer


# Criterion 9. The run reaches `done` unattended, and `hermes reduction accept`
# afterwards is an audit stamp rather than a gate (it only checks
# `review_state == 'pending'`, engine/queue.py:649) -- so nothing downstream
# distinguishes this from a sign-off unless the text itself does.
_SIMULATION = (
    "This verdict is a simulation produced by AI personas reading one file. It is "
    "not an approval, not a sign-off, and carries no authority: a human decides."
)

# A chair turn that produced nothing still gets an entry, so the transcript
# stands and the loss is visible (spec 5.3). The run then ends `failed`.
_NO_DECISION = "_(no decision delivered — the chair's turn failed; see hermes show)_"


class CommitteePlaybook:
    """A committee of personas reviewing one artifact, one speaker per phase."""

    name = "committee"

    def __init__(self) -> None:
        """Initialize the playbook with per-instance state."""
        # Instance attributes (not class attributes) so mutation stays isolated.
        self.phases = ["open", "decision"]
        self._state_by_run: dict[str, dict] = {}

    # --- per-run state (master-only) ------------------------------------

    def _state(self, run: Run) -> dict:
        """The run's mutable committee state, created on first use, LRU-bounded.

        Master-only: seed, reduce, next_phase and is_done all run in the process
        that owns the run, so this dict is the run's memory. The transport-path
        methods never read it.
        """
        s = self._state_by_run.get(run.id)
        if s is None:
            s = {
                "turn": 1,
                "opening": list(cast.SENIORITY),
                "queue": [],
                "delegation": None,
                "pending_action": None,
                # "owner", never None: with None the owner-reply rule fires before
                # the opening round and mints t01-owner -- a reply to an empty thread.
                "last_speaker": cast.OWNER,
                "closed": False,
                "verdict": "",
                "current_role": None,
                # the turn number reduce() needs; the phase name is never parsed back.
                "current_turn": 0,
                "dropped_delegation": None,
                "rechecks": [],
                # the revised copy's sha256 as seed() found it, just before a
                # junior-IC worker ran; reduce compares against this rather than
                # against the original, so a second edit that changed nothing
                # still fails its re-check (spec 7).
                "pre_edit_digest": "",
                "charge": "",
                "artifact": "",
                "revised": "",
                "roster": {},
                "max_turns": DEFAULT_MAX_TURNS,
            }
            self._state_by_run[run.id] = s
            # Evict the oldest entry when the cache exceeds the bound.
            if len(self._state_by_run) > _CACHE_MAX:
                del self._state_by_run[next(iter(self._state_by_run))]
        return s

    def _turn(self, s: dict, role: str) -> str:
        """Mint the next turn phase for `role` and advance the counter."""
        name = f"t{s['turn']:02d}-{role}"
        # reduce needs NN for the thread heading and must not parse the phase name.
        s["current_turn"] = s["turn"]
        s["turn"] += 1
        s["current_role"] = role
        # the junior IC speaks FOR the owner, so it does not trigger an owner reply
        s["last_speaker"] = cast.OWNER if role in (cast.OWNER, cast.JUNIOR) else role
        return name

    def _decision(self, s: dict) -> str:
        """Route to the terminal decision phase, chaired, losing nothing."""
        s["current_role"] = cast.CHAIR  # `decision` never passes through _turn
        if s["delegation"]:
            # only reachable when the CAP cut the edit off; reduce("decision")
            # names it in the verdict rather than dropping it silently.
            s["dropped_delegation"] = s["delegation"]
            s["delegation"] = None
        return "decision"

    # --- seeding --------------------------------------------------------

    def seed(self, run: Run, site: "Site") -> list[Ticket]:
        """Seed the current phase.

        Three shapes, dispatched on the phase the engine set. The phase name is
        display-only and is never parsed for data (§5.6):

        * ``open`` is a zero-ticket bootstrap. It checks the site, resolves the
          run's configuration once — so a mid-run environment change cannot swap
          the turn cap — builds the per-run state and writes the thread header.
          No worker runs: an owner opening would only paraphrase a document that
          every reviewer is told to read for itself.
        * ``decision`` is one ticket for the chair.
        * anything else is one ticket for ``s["current_role"]``, the speaker
          ``_turn`` recorded when it minted this phase. A junior-IC turn
          byte-copies the artifact into the revised directory first, so the
          worker only ever edits a file that is already there and ``reduce``'s
          re-check (§7) has something to hash.

        Raises:
            ValueError: the run is on a site that does not run its workers as
                local subprocesses (§8), or ``HERMES_COMMITTEE_ARTIFACT`` is
                unset or does not name an existing readable file (§6).
        """
        # §8: the thread file lives under HERMES_HOME on the master and no site
        # exposes a master-to-host push, so only a local-subprocess site works.
        if site.name != "local" and not site.name.startswith("fan-"):
            raise ValueError(
                f"the committee playbook requires a local-subprocess site, but this "
                f"run is on {site.name!r}. Use 'local' or a 'fan-<agent>' site: the "
                f"thread file lives under HERMES_HOME on the master and no site can "
                f"push it to a remote host."
            )

        phase = run.phase or self.phases[0]
        s = self._state(run)

        if phase == "open":
            raw = (os.environ.get(ENV_ARTIFACT) or "").strip()
            if not raw:
                raise ValueError(
                    f"{ENV_ARTIFACT} is unset: the committee reviews exactly one file "
                    f"and there is no default. Export "
                    f"{ENV_ARTIFACT}=/abs/path/to/the/file."
                )
            artifact = os.path.abspath(raw)
            if not (os.path.isfile(artifact) and os.access(artifact, os.R_OK)):
                raise ValueError(
                    f"{ENV_ARTIFACT}={raw!r} does not name an existing readable file "
                    f"(resolved to {artifact})."
                )

            # run.config carries exactly one key, and only from --goals
            # (engine/cli.py:375-379); nothing else ever writes that column.
            goals = run.config.get("goals") or []
            if isinstance(goals, str):
                goals = [goals]
            charge = " ".join(str(g).strip() for g in goals if str(g).strip())

            try:
                max_turns = int(os.environ.get(ENV_MAX_TURNS, DEFAULT_MAX_TURNS))
            except (TypeError, ValueError):
                max_turns = DEFAULT_MAX_TURNS

            s["charge"] = (charge or DEFAULT_CHARGE)[:cast.CHARGE_MAX]
            s["artifact"] = artifact
            s["revised"] = str(thread.revised_path(run.id, artifact))
            s["max_turns"] = max_turns
            s["roster"] = {
                role: f"{cast.persona(role)['name']}, {cast.persona(role)['title']}"
                for role in cast.CAST
            }

            # Written last: an OSError here fails the command exactly the way the
            # two ValueErrors above do, with nothing half-written behind it.
            thread.write_header(
                run.id,
                charge=s["charge"],
                artifact=s["artifact"],
                roster=[f"{role} — {who}" for role, who in s["roster"].items()],
            )
            return []

        if phase == "decision":
            role, kind, action = cast.CHAIR, "decision", None
        else:
            role = s["current_role"]
            if role == cast.JUNIOR:
                kind = "edit"
                # next_phase sets pending_action before it mints a junior turn.
                action = str(s["pending_action"] or "")
                try:
                    revised = thread.ensure_revised(run.id, s["artifact"])
                except OSError:
                    # The original was readable at `open` and has since gone.
                    # seed() is called unguarded inside the master loop
                    # (engine/dispatch.py:287), so letting this out would
                    # abandon the run `running`, with no terminal state and no
                    # event. Dispatch the turn instead: digest("") below reads
                    # as an edit that did not land, which reduce's re-check
                    # reports in the thread and the chair names in the verdict.
                    revised = thread.revised_path(run.id, s["artifact"])
                # Snapshot the copy as it stands BEFORE this worker touches it, so
                # reduce's re-check (spec 7) measures THIS edit rather than the
                # accumulated difference from the original. On the first delegation
                # the copy is a byte-copy of the original, so this is exactly the
                # comparison spec 7 describes; on the second and later ones it is
                # the only comparison that can still fail.
                s["pre_edit_digest"] = thread.digest(revised)
            else:
                kind, action = "turn", None

        return [Ticket(
            id=f"{run.id}/{phase}",
            run_id=run.id,
            phase=phase,
            state="queued",
            resource_req="cpu",
            priority=0.0,
            attempts=0,
            payload={
                "role": role,
                "title": cast.title(role, kind),
                "goal": cast.goal(
                    role,
                    charge=s["charge"],
                    artifact=s["artifact"],
                    thread=str(thread.path(run.id)),
                    revised=s["revised"],
                    action=action,
                ),
                "kind": kind,
                "action": action,
            },
        )]

    # --- the transport-path methods (spec §5.6) -------------------------
    #
    # payload_schema (engine/transport.py:324), driver (engine/transport.py:391),
    # result_schema (engine/transport.py:421) and verify (engine/queue.py:285)
    # are NOT called from the master. Under `hermes serve --host` they run in the
    # worker process, where this instance has never seen the run and
    # _state_by_run is empty. All four are therefore pure functions of their
    # arguments: no self._state(run), no per-run lookup, no file IO, no parsing
    # of the runtime phase name. Adding state to any of them silently breaks a
    # split deployment rather than failing a test.

    def payload_schema(self, phase: str) -> dict:
        """One payload shape for every ticket, whatever the phase.

        ``phase`` is ignored on purpose: one shape means no role lookup and no
        recovery of the speaker from the phase name. ``action`` is nullable and
        carries the delegated edit on a junior-IC ticket only.

        Two validator facts shape this schema (engine/contracts.py): there is no
        ``integer`` type — ``_matches_type`` has no branch for it and returns
        False for every value, 5 included — and unknown keywords (``maxLength``,
        ``pattern``, ``minItems``) are silently ignored. So nothing here counts
        or measures; the charge and action clipping is cast.py's job.
        """
        return {
            "type": "object",
            "required": ["role", "title", "goal", "kind"],
            "additionalProperties": False,
            "properties": {
                "role": {"type": "string"},
                "title": {"type": "string"},
                "goal": {"type": "string"},
                "kind": {"type": "string", "enum": ["turn", "edit", "decision"]},
                "action": {"type": ["string", "null"]},
            },
        }

    def result_schema(self, phase: str) -> dict:
        """Every speaker returns prose under ``answer``, whatever its phase.

        ``additionalProperties: true`` matches research
        (playbooks/research/playbook.py:417-428): an agent that adds keys of its
        own is not a contract failure, and a contract failure here would be
        terminal on first occurrence. The hermes-turn block lives inside the
        prose and is parsed by reduce, not by the contract.
        """
        return {
            "type": "object",
            "required": ["answer"],
            "additionalProperties": True,
            "properties": {"answer": {"type": "string"}},
        }

    def driver(self, phase: str) -> Driver:
        """Goal-only unless ``HERMES_COMMITTEE_DRIVER`` names a methodology.

        Read from the environment on every call rather than from ``run.config``:
        this method is handed a phase and nothing else, and may run in a worker
        process that never called ``seed``, so the environment is the one channel
        every process shares (playbooks/research/playbook.py:440-451 does the
        same). Whitespace is not a command.

        Every phase gets the same driver. *How* to review is the driver's
        business and does not vary by speaker; *who* you are and *what* is done
        travel in the goal.
        """
        command = (os.environ.get(ENV_DRIVER) or "").strip()
        return Driver(command=command or None, args={}, loop=None)

    def verify(self, run: Run, ticket: Ticket, result: Result, site: "Site") -> bool:
        """Always True. Deliberate — do not turn this into a form gate.

        A False sets the ticket to needs_human (engine/queue.py:283-286), and a
        needs_human ticket blocks phase advancement permanently
        (engine/dispatch.py:261-264): nothing can re-drive a run's master loop,
        because `hermes run` always creates a NEW run (engine/cli.py:382) and
        `hermes serve --host` only calls serve_loop (engine/cli.py:778). One
        empty answer would strand the committee mid-conversation with no operator
        path back. This is why it is not research's answer-text gate
        (playbooks/research/playbook.py:456-458).

        The independent re-check the no-trust invariant asks for lives in
        reduce() instead, which runs in the master (engine/dispatch.py:305), can
        hash the revised file, and records its verdict on the reduction as
        ``verified`` — visible, and named again in the decision when it failed.

        Pure by necessity: run, ticket, result and site are all it may read.
        """
        return True

    # --- the fold (master-only) -----------------------------------------

    def reduce(
        self, run: Run, phase: str, findings: list[Finding], site: "Site"
    ) -> list[Reduction]:
        """Fold one settled phase: write its thread entry, apply its gates.

        ``reduce`` is the sole writer of ``thread.md`` after the ``open`` header
        (spec 5.2), and the only place the independent re-check of a junior-IC
        edit can live (spec 7): ``verify`` runs on the transport path, and a
        ``False`` there sets the ticket ``needs_human`` (``engine/queue.py:283-286``),
        which blocks advancement with nothing able to re-drive the loop.

        For the same reason no reduction this method returns may ever carry
        ``needs_human_ticket_ids`` -- the one key the engine reads inside a
        reduction (``engine/queue.py:920``). Nothing can re-drive a stuck run:
        ``hermes run`` always creates a NEW run (``engine/cli.py:382``) and
        ``hermes serve --host`` only calls ``serve_loop`` (``engine/cli.py:778``),
        so a ``needs_human`` ticket blocks advancement
        (``engine/dispatch.py:261-264``) permanently. Do not "fix" this
        (acceptance criterion 8).

        It MUST NEVER RAISE. An exception here propagates out of
        ``engine/dispatch.py:305`` and kills the master loop mid-run, so every
        file touch is wrapped and its failure recorded under ``error`` -- the
        shape ``playbooks/dexter/playbook.py:306-311`` uses for a failed bank.
        """
        if phase == "open":
            return []  # the zero-ticket bootstrap: nothing was dispatched
        s = self._state(run)
        if phase == "decision":
            return self._reduce_decision(run, s, findings)
        return self._reduce_turn(run, s, findings)

    def _reduce_turn(
        self, run: Run, s: dict, findings: list[Finding]
    ) -> list[Reduction]:
        """One speaker's turn: the thread entry, then the gates."""
        errors: list[str] = []
        # `_turn` sets `current_role` before the phase is dispatched, so an empty
        # one means the turn cannot be attributed. Fail CLOSED: no entry under
        # someone else's name and no gates, because the old fallback (`or
        # cast.OWNER`) handed owner authority -- `close` and `delegate` -- to a
        # speaker nobody can name. The empty role matches no gate by construction.
        role = s["current_role"] or ""
        turn = s["current_turn"]
        answer = _latest_answer(findings)
        body = turnblock.strip(answer)
        # A turn whose whole answer was the block is a DELIVERED turn with no
        # prose -- not a failed one. Only a genuinely absent answer gets the
        # NO_TURN stub (spec 5.2 ties it to "no finding", not "no prose").
        if answer and not body:
            body = _SIGNALS_ONLY

        # An empty body makes `append_turn` write the NO_TURN stub, so a failed
        # turn is visible in the transcript rather than missing from it.
        if role:
            try:
                thread.append_turn(run.id, turn=turn, role=role, body=body)
            except Exception as exc:  # never raise out of reduce
                errors.append(f"thread: {exc}")
        else:
            errors.append("speaker: the turn could not be attributed")

        block = turnblock.parse(answer)

        # The gates of spec 5.4, in the one implementation Task 4 wrote and the
        # state-machine tests drive. An unattributable turn runs none of them.
        if role:
            _apply_block(s, role, block)

        # --- the independent re-check (spec 7), master-side ---------------
        # The no-trust invariant wants an independent check of an `ok` claim.
        # It cannot live in `verify` (see `reduce`'s docstring), so it lives
        # here and rides on the reduction: does the revised copy exist, and did
        # its sha256 move during THIS turn?
        #
        # The comparison is against the digest `seed` snapshotted just before
        # the worker ran -- not against the original. `ensure_revised` copies
        # once and never again, so after the first delegation lands the copy
        # differs from the original forever, and comparing to the original
        # would report `verified: true` for every later edit including one that
        # did nothing. That is precisely the silent no-op criterion 7 exists to
        # catch. On the FIRST delegation the snapshot IS the original's digest,
        # so this is exactly the check spec 7 describes.
        verified = None
        if role == cast.JUNIOR:
            verified = False
            try:
                revised = Path(s["revised"]) if s["revised"] else None
                # `seed` sets this on every junior-IC phase, so there is no
                # fallback: the only other digest available is the original's,
                # and comparing to that is the unsound reading above.
                before = s["pre_edit_digest"]
                verified = bool(
                    revised is not None
                    and revised.is_file()
                    and thread.digest(revised) != before
                )
            except Exception as exc:  # never raise out of reduce
                errors.append(f"recheck: {exc}")
            s["rechecks"].append({
                "turn": turn,
                "action": s["pending_action"] or "",
                "verified": verified,
            })

        return [Reduction(kind="turn", json={
            "role": role,
            "turn": turn,
            "delivered": bool(answer),
            # what the speaker ASKED for; whether it was honoured is visible in
            # the run's queue / closed / delegation state.
            "request_floor": bool(block.get("request_floor")),
            "delegate": bool(block.get("delegate")),
            "close": bool(block.get("close")),
            "action": block.get("action"),
            "verified": verified,
            "error": "; ".join(errors) or None,
        })]

    def _reduce_decision(
        self, run: Run, s: dict, findings: list[Finding]
    ) -> list[Reduction]:
        """The chair's turn: the verdict, every re-check by name, the disclaimer."""
        errors: list[str] = []
        answer = _latest_answer(findings)
        body = turnblock.strip(answer)

        # `s["verdict"]` is the chair's prose and nothing else -- `is_done` reads
        # it, so a failed chair turn must leave it empty and end the run failed
        # (spec 5.3). The assembled text below is what a human reads.
        s["verdict"] = body

        parts = [body or _NO_DECISION]
        for check in s["rechecks"]:
            state = "APPLIED" if check["verified"] else "DID NOT APPLY"
            parts.append(
                f"- re-check of turn {check['turn']:02d} (junior_ic): {state} "
                f"— delegated: {check['action']}"
            )
        if s["dropped_delegation"]:
            parts.append(
                "- dropped_delegation (the turn cap cut it off, no edit was made): "
                f"{s['dropped_delegation']}"
            )
        parts.append(_SIMULATION)
        text = "\n\n".join(parts)

        try:
            thread.append_decision(run.id, body=text)
        except Exception as exc:  # never raise out of reduce
            errors.append(f"thread: {exc}")

        return [Reduction(kind="decision", json={
            # the assembled text, so the reduction a reviewer reads carries the
            # re-checks and the disclaimer; empty iff the chair delivered
            # nothing, which is what ends the run failed.
            "verdict": text if body else "",
            "delivered": bool(body),
            "rechecks": [dict(check) for check in s["rechecks"]],
            "dropped_delegation": s["dropped_delegation"],
            "error": "; ".join(errors) or None,
        })]

    def next_phase(self, run: Run) -> str | None:
        """Who speaks next, or None once the decision has been taken."""
        s = self._state(run)
        if run.phase == "decision":
            return None  # -> is_done
        # a delegation outranks `close`: an edit the owner asked for still happens,
        # and costs one turn. The cap outranks BOTH, so this can never mint t31.
        if s["delegation"] and s["turn"] <= s["max_turns"]:
            s["pending_action"] = s["delegation"]
            s["delegation"] = None  # consumed exactly once, here
            return self._turn(s, cast.JUNIOR)
        if s["closed"] or s["turn"] > s["max_turns"]:
            return self._decision(s)
        if s["last_speaker"] != cast.OWNER:
            return self._turn(s, cast.OWNER)  # the owner answers every reviewer
        if s["opening"]:
            return self._turn(s, s["opening"].pop(0))
        if s["queue"]:
            return self._turn(s, s["queue"].pop(0))  # FIFO
        return self._decision(s)

    def is_done(self, run: Run) -> bool:
        """Done iff the chair's turn settled and reduce recorded a verdict.

        A chair turn that produced no finding leaves the verdict empty and the run
        ends `failed` (engine/dispatch.py:295) — deliberate: a committee that
        produced no decision did not finish.
        """
        return run.phase == "decision" and bool(self._state(run)["verdict"])


_playbook.register("committee", CommitteePlaybook())
