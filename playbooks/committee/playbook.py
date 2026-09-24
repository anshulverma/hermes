"""CommitteePlaybook — a simulated review committee over a single artifact.

Nine personas read one file and argue about it in one thread. The engine sees three
static phases (``open``, ``decision``, ``ruling``); every turn between the first two
is a phase minted at runtime as ``t{NN:02d}-{role}`` — one ticket, one speaker,
strictly serial. ``ruling`` is the human's: it seeds nothing, and a run reaches it
once the chair's verdict has been accepted or rejected.

This module is the state machine. ``next_phase`` decides who speaks next and
``is_done`` decides how the run ends. The meeting lives in a per-run dict on the
instance (``_state``), because ``run.config`` is read-only and ``run.reductions``
reaches only one phase back. So the meeting itself cannot be resumed: its turns
must all run in one master process against the one registry singleton. The
ruling can: ``is_done`` reads only the decision's reduction from the database.

Ordering is load-bearing. A pending delegation outranks ``close`` — an edit the
owner asked for still happens, and costs one turn — and the turn cap outranks
both, so ``t31`` can never be minted under ``max_turns=30``. A delegation the cap
does drop is recorded as ``dropped_delegation`` rather than lost. ``close``
itself is outranked by the opening round: the owner may not end the meeting
before every member has spoken.

Stdlib-only.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from engine import playbook as _playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket
from playbooks.committee import cast, thread, turnblock, view

if TYPE_CHECKING:  # avoid import cycle
    from engine.site import Site

ENV_ARTIFACT = "HERMES_COMMITTEE_ARTIFACT"
ENV_MAX_TURNS = "HERMES_COMMITTEE_MAX_TURNS"
ENV_DRIVER = "HERMES_COMMITTEE_DRIVER"

DEFAULT_MAX_TURNS = 30
DEFAULT_CHARGE = "Decide whether to approve this proposal."

# A turn that was delivered but carried only its hermes-turn block.
_SIGNALS_ONLY = "_(the speaker sent signals only, no prose)_"


def _apply_block(s: dict, role: str, block: dict, *, delivered: bool = True) -> None:
    """The gates of spec 5.4, applied to one settled turn.

    Enforced, not advisory, and there is exactly ONE copy of them: ``reduce``
    calls this after parsing an answer, and the state-machine tests drive it
    through ``_drive``.

    ``delivered`` is False for a turn whose worker produced no finding.
    ``driver_failed`` is terminal on first occurrence with no retry, so one
    worker hiccup is all it takes, and the turn's thread entry is the
    ``NO_TURN`` stub. Nobody may be sent to answer that: the owner's floor text
    says "answer the member who spoke last", and a real model pointed at
    ``_(no turn delivered …)_`` either hallucinates a reply or burns the turn.
    Attributing the silence to the owner is what makes ``next_phase`` move on to
    the next speaker instead.
    """
    if not delivered:
        s["last_speaker"] = cast.OWNER
        return
    if block.get("request_floor") and role not in (cast.OWNER, cast.JUNIOR, cast.CHAIR):
        # `opening` as well as `queue`: a delegated turn mints without popping,
        # so a role can still be waiting in the opening round.
        if role not in s["queue"] and role not in s["opening"]:
            s["queue"].append(role)
    if role == cast.OWNER:
        # The opening round outranks `close`. The owner's persona wants "a clear
        # decision" and "concedes fast on small things", so a worker that hears
        # one reviewer, answers it and closes produces a two-turn "committee"
        # that reaches `done` looking perfectly healthy while six members never
        # speak. The owner's goal says so too; this is what enforces it.
        if block.get("close") and not s["opening"]:
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
        # `finding.json` is whatever went into the column. A truthy non-dict --
        # a list, a bare string -- would make `(x or {}).get` an AttributeError
        # out of reduce, which abandons the run `running` with no terminal
        # state. Guard on the type, the way playbooks/dexter/playbook.py:253-260
        # does, rather than on truthiness.
        value = finding.json.get("answer") if isinstance(finding.json, dict) else None
        if isinstance(value, str) and value.strip():
            answer = value
    return answer


# Criterion 9. Only a human's accept ends the run `done`, but the verdict is
# read in thread.md and the Outputs tab, which never pass through that gate --
# so nothing there distinguishes it from a sign-off unless the text itself does.
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
        # `ruling` seeds nothing: it exists so the engine hands `is_done` the
        # decision's reductions as prior-phase data (research's `complete`).
        self.phases = ["open", "decision", "ruling"]
        self._state_by_run: dict[str, dict] = {}

    # --- per-run state (master-only) ------------------------------------

    def _state(self, run: Run) -> dict:
        """The run's mutable committee state, created on first use.

        Master-only: seed, reduce and next_phase run in the process that holds
        the meeting, so this dict is the meeting's memory. The transport-path
        methods and ``is_done`` never read it.

        Unbounded on purpose. Evicting a live run would make ``next_phase``
        re-mint ``t01-…`` (``UNIQUE constraint failed: tickets.id`` on an
        unguarded INSERT) or ``seed`` raise ``KeyError: None``, either of which
        abandons the run ``running``. ``master_loop`` has one caller and drives
        one run per process, so a bound would convert a hypothetical into a
        crash and buy nothing.
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
                # the ORIGINAL's sha256 as `open` found it. Criterion 6 promises
                # that file is inviolate, and in a live run the only thing
                # holding it is one sentence of prose against a worker running
                # --permission-mode bypassPermissions. reduce("decision")
                # re-hashes it, exactly the way a junior-IC edit is re-hashed.
                "artifact_digest": "",
                "charge": "",
                "artifact": "",
                "revised": "",
                "roster": {},
                "max_turns": DEFAULT_MAX_TURNS,
                # why the meeting stopped. Set by `_decision`, which every route
                # to the decision phase goes through; read by
                # `_reduce_decision`. Nothing else records this: the first live
                # run ended at turn 20 of a cap of 20 -- the owner closed on the
                # turn the cap would have stopped anyway -- and nothing anywhere
                # said which of the two it was.
                "ended": None,
            }
            self._state_by_run[run.id] = s
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

    def _decision(self, s: dict, ended: str) -> str:
        """Route to the terminal decision phase, chaired, losing nothing.

        ``ended`` is why the meeting stopped, decided by the caller because only
        the caller knows which branch it took. Required rather than defaulted:
        a new route to the decision that forgot to say why would otherwise ship
        a silently wrong reason.
        """
        s["current_role"] = cast.CHAIR  # `decision` never passes through _turn
        s["ended"] = ended
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
        if phase == "ruling":
            return []  # the human's step; no worker speaks
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
            # `0` and `-5` parse, and mint a committee with no turns at all: the
            # chair rules on an empty thread. That is junk the same way "soon"
            # is junk, and gets the same answer.
            if max_turns < 1:
                max_turns = DEFAULT_MAX_TURNS

            # `clip` rather than a raw slice, so an over-long charge is cut at
            # a word with an ellipsis instead of mid-word. `cast.goal` clips it
            # again; the second clip is a no-op on an already-short line.
            s["charge"] = cast.clip(charge or DEFAULT_CHARGE, cast.CHARGE_MAX)
            s["artifact"] = artifact
            s["artifact_digest"] = thread.digest(artifact)
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
                "title": cast.title(role, kind, turn=s["current_turn"], action=action),
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
        path back.

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

        For the same reason no turn's reduction may ever carry
        ``needs_human_ticket_ids``, the one key the engine reads inside a
        reduction (``engine/queue.py:920``): a held ticket mid-conversation
        wedges the run. Only the decision carries it, routing the chair's own
        ticket. The decision is terminal and its verdict is already written,
        so the hold blocks nothing but the run's end state: accept ends the
        run ``done``, reject ends it ``failed``. Any process can finish it --
        ``hermes run resume <id> --wait`` after the meeting's loop is gone --
        because ``is_done`` reads the ruling from the database.

        It MUST NEVER RAISE. An exception here propagates out of
        ``engine/dispatch.py:305`` and kills the master loop mid-run, so every
        file touch is wrapped and its failure recorded under ``error`` -- the
        shape ``playbooks/dexter/playbook.py:306-311`` uses for a failed bank.
        """
        if phase in ("open", "ruling"):
            return []  # a zero-ticket phase: nothing was dispatched
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
        # one means the turn cannot be attributed. Fail CLOSED -- no entry under
        # someone else's name, no gates. A fallback to `cast.OWNER` would hand
        # owner authority (`close`, `delegate`) to a speaker nobody can name.
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

        # The gates of spec 5.4. An unattributable turn runs none of them.
        if role:
            _apply_block(s, role, block, delivered=bool(answer))

        # `stance` is not a gate -- it steers nothing, so it is not in
        # `_apply_block`. It rides on the turn reduction below and nowhere else:
        # the accumulator that used to sit here duplicated what every turn
        # reduction already carries (role, turn, stance) and had no reader in
        # production code on either side of the seam.

        # --- the independent re-check (spec 7), master-side ---------------
        # The no-trust invariant wants an independent check of an `ok` claim. It
        # cannot live in `verify` (see `reduce`'s docstring), so it rides on the
        # reduction instead: does the revised copy exist, and did its sha256
        # move during THIS turn?
        #
        # RULE: compare against the digest `seed` snapshotted just before the
        # worker ran, never against the original. `ensure_revised` copies once
        # and never again, so after the first delegation the copy differs from
        # the original forever and every later edit -- including one that did
        # nothing -- would read as verified. On the FIRST delegation the
        # snapshot IS the original's digest, which is the check spec 7 describes.
        verified = None
        if role == cast.JUNIOR:
            verified = False
            try:
                revised = Path(s["revised"]) if s["revised"] else None
                # `seed` sets this on every junior-IC phase; there is no
                # fallback, per the RULE above.
                before = s["pre_edit_digest"]
                # An empty `before` is not a digest -- `digest` of a zero-byte
                # file is e3b0c442..., never "" -- it means the snapshot itself
                # failed (`seed`'s OSError path: the original vanished before
                # any copy was made). Without the clause, a worker that INVENTED
                # the revised file from nothing hashes to something != "" and is
                # reported verified, inverting the one no-trust check (spec 7).
                verified = bool(
                    before
                    and revised is not None
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
            # The prose, duplicated out of thread.md and into the reduction. A
            # reader of this run has the transcript; a READER OF THE DATABASE
            # had not one word of what anyone said (spec 6).
            "body": body,
            # Uncoerced: absent stays absent, the rule the whole block obeys. A
            # persona that stated no stance has none, never a neutral one.
            "stance": block.get("stance"),
            # Both paths ride on EVERY turn reduction, which looks redundant
            # against the decision reduction that also carries them. It is not:
            # `view_data` runs in the SERVER process, where this instance has
            # never seen the run and `_state_by_run` is empty, so the paths
            # cannot be read off state there -- reductions are the only channel.
            # Do not "optimise" these away to the decision reduction alone.
            "artifact": s["artifact"],
            "revised": s["revised"],
            # The turn cap `seed` resolved, for the same reason and by the same
            # route as the two paths above: `view_data` runs in the SERVER
            # process, and reading HERMES_COMMITTEE_MAX_TURNS there gets THAT
            # process's value. A `hermes serve` started without it rendered
            # "turn 20 of 30" for a run that capped at 20 and used all of it.
            "cap": s["max_turns"],
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

        # The other half of criterion 6, and the half nothing else re-checks: the
        # ORIGINAL is promised inviolate, and in a live run that promise is one
        # sentence of prose against a worker running bypassPermissions. Symmetric
        # with the junior-IC re-check above -- snapshot at `open`, compare here,
        # and name a mismatch the way a failed re-check is named. `None` means
        # "no artifact resolved", which only a state that never ran `open` sees.
        intact = None
        if s["artifact"]:
            intact = bool(s["artifact_digest"]) and (
                thread.digest(s["artifact"]) == s["artifact_digest"]
            )

        parts = [body or _NO_DECISION]
        for check in s["rechecks"]:
            state = "APPLIED" if check["verified"] else "DID NOT APPLY"
            parts.append(
                f"- re-check of turn {check['turn']:02d} (junior_ic): {state} "
                f"— delegated: {check['action']}"
            )
        if intact is False:
            parts.append(
                "- re-check of the original artifact: CHANGED DURING THE REVIEW "
                f"— it was to be left untouched: {s['artifact']}"
            )
        if s["dropped_delegation"]:
            parts.append(
                "- dropped_delegation (the turn cap cut it off, no edit was made): "
                f"{s['dropped_delegation']}"
            )
        if s["queue"]:
            # Symmetric with dropped_delegation: a floor request the close or the
            # cap never got to is a fact about this committee's output, and the
            # queue is otherwise discarded without a word.
            parts.append(
                "- dropped_floor_requests (the review ended before their turn "
                f"came): {', '.join(s['queue'])}"
            )
        parts.append(_SIMULATION)
        text = "\n\n".join(parts)

        try:
            thread.append_decision(run.id, body=text)
        except Exception as exc:  # never raise out of reduce
            errors.append(f"thread: {exc}")

        return [Reduction(kind="decision", json={
            # The verdict goes to a human: the chair's own ticket (seed mints
            # it as `<run>/decision`) is held `needs_human`, so the run ends
            # `done` on accept and `failed` on reject. Everything above is
            # already banked; only the terminal state waits. A failed chair
            # has nothing to rule on and routes nothing.
            "needs_human_ticket_ids": [f"{run.id}/decision"] if body else [],
            # the assembled text, so the reduction a reviewer reads carries the
            # re-checks and the disclaimer; empty iff the chair delivered nothing.
            "verdict": text if body else "",
            # read by `is_done`: a chair that delivered nothing ends the run failed
            "delivered": bool(body),
            "rechecks": [dict(check) for check in s["rechecks"]],
            "artifact_intact": intact,
            "dropped_delegation": s["dropped_delegation"],
            "dropped_floor_requests": list(s["queue"]),
            # Why the meeting stopped. A chair that delivered nothing outranks
            # whatever routed the run here: that IS how this meeting ended, and
            # it is the ending the operator has to act on. The fallback covers a
            # `decision` state that never went through `next_phase` -- reachable
            # only by seeding the phase directly.
            "ended": "chair turn failed" if not body else (s["ended"] or "queue empty"),
            # Same reason as the turn reduction: server-side `view_data` cannot
            # read instance state.
            "artifact": s["artifact"],
            "revised": s["revised"],
            "error": "; ".join(errors) or None,
        })]

    def next_phase(self, run: Run) -> str | None:
        """Who speaks next, then the human's ruling, then None."""
        if run.phase == "decision":
            return "ruling"  # reached once the human has ruled on the held verdict
        if run.phase == "ruling":
            return None  # -> is_done
        s = self._state(run)
        # a delegation outranks `close`: an edit the owner asked for still happens,
        # and costs one turn. The cap outranks BOTH, so this can never mint t31.
        if s["delegation"] and s["turn"] <= s["max_turns"]:
            s["pending_action"] = s["delegation"]
            s["delegation"] = None  # consumed exactly once, here
            return self._turn(s, cast.JUNIOR)
        if s["closed"] or s["turn"] > s["max_turns"]:
            # Mirrors the `or`: an owner that closed is why the meeting stopped,
            # even when the cap would have stopped it on the next hop anyway.
            return self._decision(s, "owner closed" if s["closed"] else "turn cap")
        if s["last_speaker"] != cast.OWNER:
            return self._turn(s, cast.OWNER)  # the owner answers every reviewer
        if s["opening"]:
            return self._turn(s, s["opening"].pop(0))
        if s["queue"]:
            return self._turn(s, s["queue"].pop(0))  # FIFO
        return self._decision(s, "queue empty")

    def is_done(self, run: Run) -> bool:
        """Done iff the chair delivered a verdict and a human accepted it.

        Read from the database, never from this instance: the human may rule
        long after the process that held the meeting is gone. A chair that
        delivered nothing, or a rejected verdict, ends the run `failed`.
        """
        return run.phase == "ruling" and any(
            r.kind == "decision" and r.json.get("delivered") and r.review_state == "accepted"
            for r in run.reductions
        )

    # --- the view seam (spec §4) ----------------------------------------
    # Optional and duck-typed: never declared on the Playbook Protocol, so
    # adding them cannot un-conform dexter or research, and the engine never
    # calls them. The server discovers them with getattr.

    def view_asset(self) -> Path | None:
        """Absolute path to the built committee view bundle, or None."""
        return view.view_asset()

    def view_data(self, run: Run, reductions: list[Reduction]) -> dict:
        """Everything the committee view renders, from reductions alone."""
        return view.view_data(run, reductions)


_playbook.register("committee", CommitteePlaybook())
