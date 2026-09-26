"""CommitteePlaybook — a simulated review committee over a single artifact.

Nine personas read one file and argue about it in one thread. The engine sees three
static phases (``open``, ``decision``, ``ruling``); every turn between the first two
is a phase minted at runtime as ``t{NN:02d}-{role}`` — one ticket, one speaker,
strictly serial. Before ``t01`` three selection phases (``s1-owner``,
``s2-manager``, ``s3-senior_director``) seat the committee, outside the turn
count. ``ruling`` is the human's: it seeds nothing, and a run reaches it
once the chair's verdict has been accepted or rejected.

This module is the state machine. ``next_phase`` decides who speaks next and
``is_done`` decides how the run ends. The meeting lives in a per-run dict on the
instance (``_state``), because ``run.config`` is read-only and ``run.reductions``
reaches only one phase back. So the meeting itself cannot be resumed: its turns
must all run in one master process against the one registry singleton, and a
process that finds one under way ends the run ``failed`` (``_lost``). The ruling
can be: ``is_done`` reads only the decision's reduction from the database.

Ordering is load-bearing. A pending delegation outranks ``close`` — an edit the
owner asked for still happens, and costs one turn — and the turn cap outranks
both, so ``t31`` can never be minted under ``max_turns=30``. A delegation the cap
does drop is recorded as ``dropped_delegation`` rather than lost. ``close``
itself is outranked by the opening round: the owner may not end the meeting
before every member has spoken.

Stdlib-only.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

from engine import playbook as _playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket
from playbooks.committee import cast, selection, thread, turnblock, view, voice

if TYPE_CHECKING:  # avoid import cycle
    from engine.site import Site

ENV_ARTIFACT = "HERMES_COMMITTEE_ARTIFACT"
ENV_MAX_TURNS = "HERMES_COMMITTEE_MAX_TURNS"
ENV_DRIVER = "HERMES_COMMITTEE_DRIVER"

DEFAULT_MAX_TURNS = 30
DEFAULT_CHARGE = "Decide whether to approve this proposal."

# A turn that was delivered but carried only its hermes-turn block.
_SIGNALS_ONLY = "_(the speaker sent signals only, no prose)_"
# A selector's answer that was its hermes-selection block and nothing else (I2).
_SEAT_LIST_ONLY = "_(the seat list was the whole answer)_"

# A chair's list that cannot seat anyone, which she retakes before any fallback (D3).
_UNUSABLE = ("no_block", "unparseable", "too_few")

# The chair's phase and its retakes (C8: take k of a phase is `{base}-take{k}`).
# Everything that used to compare against the literal "decision" checks
# membership here instead, so a verdict kept under `decision-take2` is still
# the decision. `self.phases` stays open/decision/ruling.
DECISION_PHASES: tuple[str, ...] = ("decision",) + tuple(
    f"decision-take{k}" for k in range(2, voice.MAX_TAKES + 1)
)

# What the final selection reduction adds (selection C5, and the counts of the
# FIX_SA amendment): `resolve` and `fallback` return exactly these.
_FINAL_KEYS = (
    "seated", "reviewers", "considered", "considered_dropped", "invalid_dropped", "fallback",
)

# voice's rules on the hermes-turn block, which `_reduce_select` never applies
_TURN_BLOCK_RULES = ("stance_too_long", "action_too_long")


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
            s["delegation_turn"] = s["current_turn"]


def _apply_selection(s: dict, resolved: dict) -> None:
    """Install the ratified committee on the run's state (selection D1, D2).

    After ``open`` seats the fixed four, this is the only writer of
    ``roster``, ``reviewers``, ``opening`` and ``considered``, and only ``_reduce_select``
    calls it, on the chair's kept take. It also sets ``max_turns`` to
    2 x reviewers + 16 unless ``cap_explicit`` (D5). ``resolved`` is the dict
    ``selection.resolve`` or ``selection.fallback`` returns. Everything is
    built before anything is assigned, so a malformed ``resolved`` raises with
    the state untouched and the caller installs the fallback: ``opening`` is
    inside ``roster`` before t01 is seeded.
    """
    roster = {seat["role"]: seat for seat in resolved["seated"]}
    reviewers = list(resolved["reviewers"])
    # D5: an unset cap grows with the committee, two turns per reviewer plus
    # sixteen (3 -> 22, 7 -> 30, 12 -> 40). When every owner reply delegates,
    # reviewer k opens at turn 3k-2 and the last edit is turn 3R, which leaves
    # 16-R >= 4 turns for the floor at R <= 12. An explicit
    # HERMES_COMMITTEE_MAX_TURNS stays literal, even below 3R-2.
    cap = s["max_turns"]
    if not s["cap_explicit"]:
        cap = 2 * len(reviewers) + 16
    # who each seat speaks for, read into its goal by seed (D1)
    considered = [dict(entry) for entry in resolved["considered"]]
    # `opening` a copy: the opening round is popped as it runs, `reviewers` never is
    s.update(roster=roster, reviewers=reviewers, opening=list(reviewers), max_turns=cap,
             considered=considered)


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


def _copy_digest(data: bytes | None) -> str:
    """The revised copy's state for the report-only retake check (voice D3.6).

    ``data`` is ``thread.read_regular``'s bytes. No regular file reads as
    ``"absent"``, never ``""``: a take 1 that left no copy must still catch a
    retake that writes one.
    """
    return hashlib.sha256(data).hexdigest() if data is not None else "absent"


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

_LOST = (
    "the meeting cannot be resumed: its floor queue and cast lived in the process "
    "that held it, which is gone. thread.md keeps every turn up to here."
)

_LOST_OPEN = (
    "the meeting cannot be started here: the process that opened it, and resolved "
    "its charge, artifact and turn cap, is gone. Start a new run."
)


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
                # the owner turn that set `delegation`, so the junior turn that
                # applies it -- or the decision that drops it -- can name it.
                "delegation_turn": None,
                "pending_action": None,
                # "owner", never None: with None the owner-reply rule fires before
                # the opening round and mints t01-owner -- a reply to an empty thread.
                "last_speaker": cast.OWNER,
                "closed": False,
                "current_role": None,
                # the turn number reduce() needs; the phase name is never parsed back.
                "current_turn": 0,
                "dropped_delegation": None,
                "dropped_delegation_turn": None,
                # Provenance of the turn being minted, written on its reduction:
                # the reviewer turn an owner turn answers, and the owner turn a
                # junior-IC turn applies. `_turn` resets both on every mint, so
                # each is an int only on its own kind of turn.
                "answers_turn": None,
                "delegated_by_turn": None,
                # Set by a junior-IC seed when the revised copy could not be
                # made from doc/00-original; that turn's reduction records it.
                "snapshot_note": None,
                "rechecks": [],
                # the revised copy's sha256 as seed() found it, just before a
                # junior-IC take 1 ran (a retake keeps it: its re-check still
                # measures take 1's edit); reduce compares against this rather than
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
                # Retakes (voice D3). `base` is the take-1 phase name of the
                # speaking phase in progress; take k is `{base}-take{k}`, and
                # the owner's or a reviewer's one image file is `{base}.svg|png`.
                "base": "",
                "take": 1,
                # the note for the NEXT take, set when reduce discards one;
                # `_retake` moves it into `note`, which seed hands the worker.
                "retake": None,
                "note": None,
                # the discarded take kept in reserve: {"answer", "take"}. A
                # retake that delivers nothing falls back to it.
                "held": None,
                # `takes/<base>-take<n>.md`, the discarded take's body as
                # `_discard` wrote it, which the next take's goal names ("" when
                # the write was refused); and the image stem this phase's goal
                # offered ("" for none), which a retake note names.
                "last_take": "",
                "image": "",
                # the revised copy's `_copy_digest` after a discarded junior
                # take 1, so a report-only retake that edits again is caught.
                "edit_digest": "",
                # Selection (selection D1, C3). `current_kind` is what seed and
                # reduce dispatch on, state-held: None until the first mint,
                # then "select", "turn" (junior turns too) or "decision".
                "current_kind": None,
                # the stage in progress (1-3), and the next one to mint. 4 means
                # selection is done: `open` sets 1, so a state that never saw
                # `open` mints no s-phase.
                "current_stage": None,
                "selection_next": 4,
                # one {stage, role, delivered, doc, code} per kept stage take
                "stages": [],
                # HERMES_COMMITTEE_MAX_TURNS was set explicitly (D5)
                "cap_explicit": False,
                # the run's reviewers in opening order: the default seven until
                # the chair's list is installed
                "reviewers": list(cast.SENIORITY),
                # the ratified committee's considered stakeholders; a seat's goal
                # names the ones it represents (selection D1)
                "considered": [],
            }
            self._state_by_run[run.id] = s
        return s

    def _lost(self, run: Run, s: dict) -> str | None:
        """Why this process cannot hold the meeting (a ``resume --wait``), or None.

        At ``open``, this process never ran it when ``selection_next`` is still
        4: ``open`` sets 1, and only minting s3 sets 4 again, past ``open``.
        Without it there is no charge, artifact or cap, and ``next_phase`` would
        skip selection and hold the meeting on an empty state. Past ``open``, a
        process that held it always has a speaker on record: ``_select``,
        ``_turn`` and ``_decision`` set one before the phase is dispatched.
        Without one the floor queue and the cast are gone, and ``next_phase``
        would re-mint ``t01`` over a ticket that exists.
        """
        if run.phase == "open":
            return _LOST_OPEN if s["selection_next"] == 4 else None
        return _LOST if run.phase is not None and s["current_role"] is None else None

    def _begin(self, s: dict, base: str) -> None:
        """Start a speaking phase: take 1 of ``base``, nothing pending or held.

        Every mint of a speaking phase calls this with its take-1 name, here and
        in any later loop, so retake and image names never repeat.
        """
        s.update(base=base, take=1, note=None, held=None, edit_digest="", last_take="", image="")

    def _retake(self, s: dict) -> str:
        """Mint the next take of the phase in progress: same speaker, same turn.

        Reads only ``base`` and ``take``. It never goes through ``_turn``, so the
        turn counter, ``current_turn``, ``last_speaker`` and the cap are
        untouched: a retake is the same turn said again, not a new one.
        """
        s["take"] += 1
        s["note"], s["retake"] = s["retake"], None
        return f"{s['base']}-take{s['take']}"

    def _turn(
        self, s: dict, role: str, *, answers: int | None = None,
        delegated_by: int | None = None,
    ) -> str:
        """Mint the next turn phase for `role` and advance the counter.

        ``answers`` and ``delegated_by`` are recorded on EVERY mint, so a
        reviewer turn resets both to None. The view prefers these recorded
        links to turn order, which is only true of today's ``next_phase``.
        """
        name = f"t{s['turn']:02d}-{role}"
        s["answers_turn"] = answers
        s["delegated_by_turn"] = delegated_by
        # reduce needs NN for the thread heading and must not parse the phase name.
        s["current_turn"] = s["turn"]
        s["turn"] += 1
        s["current_role"] = role
        s["current_kind"] = "turn"  # every role, the junior IC included
        # the junior IC speaks FOR the owner, so it does not trigger an owner reply
        s["last_speaker"] = cast.OWNER if role in (cast.OWNER, cast.JUNIOR) else role
        self._begin(s, name)
        return name

    def _decision(self, s: dict, ended: str) -> str:
        """Route to the terminal decision phase, chaired, losing nothing.

        ``ended`` is why the meeting stopped, decided by the caller because only
        the caller knows which branch it took. Required rather than defaulted:
        a new route to the decision that forgot to say why would otherwise ship
        a silently wrong reason.
        """
        s["current_role"] = cast.CHAIR  # `decision` never passes through _turn
        s["current_kind"] = "decision"
        s["ended"] = ended
        self._begin(s, "decision")
        if s["delegation"]:
            # only reachable when the CAP cut the edit off; reduce("decision")
            # names it in the verdict rather than dropping it silently.
            s["dropped_delegation"] = s["delegation"]
            s["dropped_delegation_turn"] = s["delegation_turn"]
            s["delegation"] = None
        return "decision"

    def _select(self, s: dict, stage: int) -> str:
        """Mint selection stage ``stage`` (1-3): its selector seats the committee.

        Outside the meeting: it never touches ``turn``, ``current_turn``,
        ``last_speaker``, ``max_turns``, ``opening`` or ``queue``, so the owner
        still "spoke last" when s3 settles and the next phase is ``t01``,
        numbered exactly as without selection. ``_begin`` makes the stage name
        the base, so a retake is ``s{N}-{role}-take{k}`` and the selector's one
        image is ``s{N}-{role}.svg|png``.
        """
        role = ("owner", "manager", "senior_director")[stage - 1]
        name = f"s{stage}-{role}"
        self._begin(s, name)
        s["current_role"] = role
        s["current_kind"] = "select"
        s["current_stage"] = stage
        s["selection_next"] = stage + 1
        return name

    # --- seeding --------------------------------------------------------

    def seed(self, run: Run, site: "Site") -> list[Ticket]:
        """Seed the current phase.

        Four shapes, dispatched on the phase the engine set. The phase name is
        display-only and is never parsed for data (§5.6):

        * ``open`` is a zero-ticket bootstrap. It checks the site, resolves the
          run's configuration once — so a mid-run environment change cannot swap
          the turn cap — builds the per-run state and writes the thread header.
          No worker runs: an owner opening would only paraphrase a document that
          every reviewer is told to read for itself.
        * ``decision``, or a retake of it (``DECISION_PHASES``), is one ticket
          for the chair.
        * a selection stage (``current_kind`` "select") is one ticket for its
          selector, with the stage's own title and goal.
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
                max_turns = int(os.environ.get(ENV_MAX_TURNS, ""))
            except (TypeError, ValueError):
                max_turns = 0
            # `0` and `-5` parse, and mint a committee with no turns at all: the
            # chair rules on an empty thread. That is junk the same way "soon"
            # is junk, and gets the same answer: unset. Only an int >= 1 is
            # explicit, and it is used as-is (selection D5). An unset cap is a
            # provisional 30 until `_apply_selection` sizes it to the committee.
            cap_explicit = max_turns >= 1
            if not cap_explicit:
                max_turns = DEFAULT_MAX_TURNS

            # `clip` rather than a raw slice, so an over-long charge is cut at
            # a word with an ellipsis instead of mid-word. `cast.goal` clips it
            # again; the second clip is a no-op on an already-short line.
            s["charge"] = cast.clip(charge or DEFAULT_CHARGE, cast.CHARGE_MAX)
            s["artifact"] = artifact
            # One read serves both: the digest `reduce("decision")` re-checks
            # and the doc/00-original snapshot are the same bytes, by construction.
            data = Path(artifact).read_bytes()
            s["artifact_digest"] = hashlib.sha256(data).hexdigest()
            s["revised"] = str(thread.revised_path(run.id, artifact))
            s["max_turns"] = max_turns
            s["cap_explicit"] = cap_explicit
            # The fixed four (Q5), as seat records; the chair's ratified list
            # replaces this at the final resolve. Selection runs first.
            s["roster"] = selection.fixed_seats()
            s["selection_next"] = 1

            # Written last, snapshot then header: an OSError from either fails
            # the command exactly the way the two ValueErrors above do, and a
            # failed snapshot leaves no header claiming the meeting opened.
            thread.write_snapshot(run.id, thread.snapshot_key(artifact, None), data)
            thread.images_dir(run.id)
            thread.write_header(
                run.id,
                charge=s["charge"],
                artifact=s["artifact"],
                # the legacy `- role — Name, Title` lines eval's parser reads
                roster=[f"{r} — {p['name']}, {p['title']}" for r, p in s["roster"].items()],
                rules=voice.RULES,
                library=cast.LIBRARY.items(),
            )
            return []

        if phase in DECISION_PHASES:
            role, kind, action = cast.CHAIR, "decision", None
        elif s["current_kind"] == "select":
            # A selector seats the committee (selection D1): no action and no
            # revised copy. The stage is state-held; the phase name is never parsed.
            role, kind, action = s["current_role"], "select", None
        else:
            role = s["current_role"]
            kind, action = "turn", None
            if role == cast.JUNIOR:
                # next_phase sets pending_action before it mints a junior turn.
                # A retake keeps kind "edit" and the action (the payload keys
                # are frozen), so its card still names the edit.
                kind, action = "edit", str(s["pending_action"] or "")
            if role == cast.JUNIOR and s["take"] == 1:
                # Take 1 only. A retake is report-only (its goal forbids every
                # write), and its re-check still measures take 1's edit, so the
                # copy is never re-made and the snapshot stays the one taken
                # before take 1 ran.
                try:
                    revised, s["snapshot_note"] = thread.ensure_revised(
                        run.id, s["artifact"], s["artifact_digest"]
                    )
                except OSError:
                    # No copy could be made: the original AND its doc/00-original
                    # snapshot have both gone since `open`, or the write into
                    # revised/ failed.
                    # seed() is called unguarded inside the master loop
                    # (engine/dispatch.py:287), so letting this out would
                    # abandon the run `running`, with no terminal state and no
                    # event. Dispatch the turn instead: digest("") below reads
                    # as an edit that did not land, which reduce's re-check
                    # reports in the thread and the chair names in the verdict.
                    revised = thread.revised_path(run.id, s["artifact"])
                    s["snapshot_note"] = None
                # Snapshot the copy as it stands BEFORE this worker touches it, so
                # reduce's re-check (spec 7) measures THIS edit rather than the
                # accumulated difference from the original. On the first delegation
                # the copy is a byte copy of the bytes `open` hashed --
                # doc/00-original only while its digest still matches, else the
                # live file -- so this is exactly the comparison spec 7
                # describes; on the second and later ones it is the only
                # comparison that can still fail.
                s["pre_edit_digest"] = thread.digest(revised)

        # The owner's, a reviewer's and a selector's one image, named for the
        # phase. Made here, 0700, not by the worker (0755): a run opened before
        # `open` made the folder has none. A folder that is refused (a planted
        # symlink or file) offers no image rather than failing the run.
        image = ""
        if kind in ("turn", "select") and s["base"]:
            try:
                thread.images_dir(run.id)
                image = s["base"]
            except (OSError, ValueError):
                pass
        s["image"] = image  # what a retake note names as the one passing reference

        if kind == "select":
            # The selector's own title and goal (selection D7).
            title = cast.title(role, "select", turn=s["current_stage"], take=s["take"])
            goal = cast.select_goal(
                role,
                stage=s["current_stage"],
                charge=s["charge"],
                artifact=s["artifact"],
                thread=str(thread.path(run.id)),
                image=image,
                retake=s["note"],
                last_take=s["last_take"],
            )
        else:
            # Named through the run's own committee: a library or derived seat
            # is not in cast.CAST, and {} (a state that never ran `open`) is CAST.
            # A seat's goal names the considered stakeholders it speaks for (D1).
            speaks_for = [entry["stakeholder"] for entry in s["considered"]
                          if entry.get("represented_by") == role]
            title = cast.title(
                role, kind, turn=s["current_turn"], action=action, take=s["take"],
                roster=s["roster"] or None,
            )
            goal = cast.goal(
                role,
                charge=s["charge"],
                artifact=s["artifact"],
                thread=str(thread.path(run.id)),
                revised=s["revised"],
                action=action,
                image=image,
                retake=s["note"],
                last_take=s["last_take"],
                roster=s["roster"] or None,
                speaks_for=speaks_for,
            )

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
                "title": title,
                "goal": goal,
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
                "kind": {"type": "string", "enum": ["turn", "edit", "decision", "select"]},
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
        if phase == "ruling":
            return []  # a zero-ticket phase: nothing was dispatched
        s = self._state(run)
        lost = self._lost(run, s)
        if lost:
            return [Reduction(kind="lost", json={"error": lost})]
        if phase == "open":
            return []  # zero tickets too, but a process that never opened it is lost
        if phase in DECISION_PHASES:
            return self._reduce_decision(run, s, findings, phase)
        if s["current_kind"] == "select":
            return self._reduce_select(run, s, findings)
        return self._reduce_turn(run, s, findings)

    # --- the voice gate (voice D3) --------------------------------------

    def _grade(
        self, run: Run, s: dict, role: str, answer: str, *, file_images: bool = True
    ) -> tuple[bool, dict | None, list[str], list[str]]:
        """(discard, metrics, violations, flags) for one take. Never raises.

        Runs BEFORE any side effect of the take: a take sent back never reaches
        thread.md, never moves a gate, never runs a re-check. metrics is None
        for an undelivered or signals-only take, which is never discarded.
        ``file_images=False`` refuses every file image (a phase whose images/
        name could collide), so a file reference there forces a retake. So
        does an images folder that is absent or that ``thread.images_dir``
        refuses (a planted symlink or file): nothing reached through it is the
        speaker's own file. Grading only looks; it never makes the folder.
        """
        try:
            body = turnblock.strip(answer)
            if not answer or not body:
                return False, None, [], []
            metrics = voice.measure(body, role)
            metrics.update(turnblock.lengths(answer))
            images = metrics["images"]
            folder = None
            if file_images and any(image["kind"] == "image" for image in images):
                try:
                    folder = thread.images_dir(run.id, create=False)
                except (OSError, ValueError):
                    folder = None
            metrics["images"] = (
                voice.check_images(images, folder, s["base"]) if folder is not None
                else [{**image, "ok": image["kind"] == "mermaid"} for image in images]
            )
            violations = voice.violations(metrics, role)
            flags = voice.flags(metrics, role)
        except Exception:  # never raise out of reduce
            return False, None, [], []
        return bool(violations) and s["take"] < voice.MAX_TAKES, metrics, violations, flags

    def _discard(
        self, run: Run, s: dict, role: str, answer: str, metrics: dict | None,
        violations: list[str], flags: list[str], turn: int | None,
        extra: dict | None = None,
    ) -> list[Reduction]:
        """Hold a take that broke a hard rule and ask the same speaker again.

        Writes nothing to thread.md and applies no gate. The take survives on
        its ``take`` reduction, which carries no ``artifact``, ``revised`` or
        ``cap`` (the keys the kind-agnostic readers scan) and never routes a
        ticket, and its body in ``takes/<base>-take<n>.md``, which the retake's
        goal names so the speaker keeps what it said and fixes only the rules.
        A refused or failed write names no file and is the take's ``error``.
        ``extra`` is a later loop's own keys (``stage``, ``seq``).
        """
        block = turnblock.parse(answer)
        body = turnblock.strip(answer)
        s["held"] = {"answer": answer, "take": s["take"]}
        s["retake"] = voice.note(metrics or {}, violations, take=s["take"] + 1, image=s["image"])
        error = None
        try:
            s["last_take"] = thread.write_take(run.id, f"{s['base']}-take{s['take']}.md", body)
        except Exception as exc:  # never raise out of reduce
            s["last_take"], error = "", f"takes: {exc}"
        doc = {
            "phase": s["base"],
            "role": role,
            "turn": turn,
            "take": s["take"],
            "kept": False,
            "delivered": True,
            "body": body,
            "stance": block.get("stance"),
            "action": block.get("action"),
            "voice": metrics,
            "violations": violations,
            "flags": flags,
            "error": error,
        }
        doc.update(extra or {})
        return [Reduction(kind="take", json=doc)]

    def _keep(
        self, run: Run, s: dict, role: str, answer: str, metrics: dict | None,
        violations: list[str], flags: list[str], *, file_images: bool = True,
    ) -> tuple[str, int, int, dict | None, list[str], list[str]]:
        """(answer, take, takes, metrics, violations, flags) of the take to keep.

        This take, unless it delivered nothing and an earlier take is held: then
        the held take is kept, graded again (with the caller's ``file_images``),
        with ``retake_failed`` added.
        """
        takes = take = s["take"]
        if metrics is None and s["held"]:
            answer, take = s["held"]["answer"], s["held"]["take"]
            _, metrics, violations, flags = self._grade(
                run, s, role, answer, file_images=file_images
            )
            violations = [*violations, "retake_failed"]
        s["held"] = s["retake"] = None
        return answer, take, takes, metrics, violations, flags

    @staticmethod
    def _unusable(stage: int, take: int, answer: str) -> str | None:
        """The code of a chair's delivered take whose list cannot seat anyone
        (``no_block``, ``unparseable``, ``too_few``) while she has a take left,
        else None. Stages 1-2 never fall back, so they are never asked again for
        a list (D3). Never raises."""
        if stage != 3 or take >= voice.MAX_TAKES or not answer:
            return None
        try:
            doc, code = selection.parse(answer)
            code = selection.stage_code(True, code, selection.validate(doc, cast.LIBRARY)[0])
        except Exception:  # never raise out of reduce; the kept path records it
            return None
        return code if code in _UNUSABLE else None

    def _reduce_select(
        self, run: Run, s: dict, findings: list[Finding]
    ) -> list[Reduction]:
        """One selector's stage: the list in the thread and on a selection reduction.

        Voice grades the RAW answer, fences intact (its measure skips fenced
        blocks); fences are stripped only for the thread and the reduction
        ``body``. A take that breaks voice's hard rules is discarded and retaken
        under the stage's base (s1-owner-take2); so is a chair's take whose list
        cannot seat anyone, with a note of the playbook's own, until her last
        take (D3). A retake that delivers nothing keeps the held take, flagged
        retake_failed. Only the kept take's list is the stage's.
        No ``_apply_block``: a selector's request_floor, delegate and close are
        ignored. Never raises: every parse and file touch is wrapped, and
        exactly one ``selection`` reduction comes back per kept take (C5). It routes
        nothing (Q3), so it carries no ``needs_human_ticket_ids``, and no
        ``artifact``, ``revised`` or ``turn`` for the kind-agnostic readers.
        """
        errors: list[str] = []
        role, stage = s["current_role"], s["current_stage"]
        answer = _latest_answer(findings)
        _, metrics, violations, flags = self._grade(run, s, role, answer)
        # A selector is never asked for a hermes-turn block and none is applied,
        # so its stance and action lengths are no rule of hers.
        violations = [v for v in violations if v not in _TURN_BLOCK_RULES]
        discard = bool(violations) and s["take"] < voice.MAX_TAKES
        if discard:
            # Before any parse, thread write or `stages` append, so a discarded
            # take's list is never the stage's. `_retake` re-mints the stage off
            # `s["base"]` (`s2-manager-take2`); no meeting counter moves.
            return self._discard(
                run, s, role, answer, metrics, violations, flags, None,
                extra={"stage": stage},
            )
        unusable = self._unusable(stage, s["take"], answer)
        if unusable:
            # D3: the chair's list is final, so one that cannot seat anyone is
            # asked for again before the run falls back; only her last take
            # falls back. The note is the playbook's, not voice's, and counts
            # seats as her block does: the fixed four are never listed in it.
            out = self._discard(
                run, s, role, answer, metrics, violations, flags, None,
                extra={"stage": stage, "code": unusable},
            )
            s["retake"] = (
                f"Retake {s['take'] + 1} of {voice.MAX_TAKES}. No usable seat list: "
                f"{selection.fallback_words(unusable)}. End your answer with the "
                f"```hermes-selection block at column 0, {selection.MIN_REVIEWERS - 2} to "
                f"{selection.MAX_REVIEWERS - 2} seats besides the fixed four."
            )
            return out
        answer, take, takes, metrics, violations, flags = self._keep(
            run, s, role, answer, metrics, violations, flags
        )
        violations = [v for v in violations if v not in _TURN_BLOCK_RULES]  # a held take regraded
        # Off the answer `_keep` returns: a retake that delivered nothing keeps
        # the held take, which WAS delivered, so stage 3's code comes from its
        # list, never "no_answer".
        delivered = bool(answer)
        try:
            doc, code = selection.parse(answer)
            seats, invalid = selection.validate(doc, cast.LIBRARY)
            not_seated = selection.not_seated(doc)
            code = selection.stage_code(delivered, code, seats)
        except Exception as exc:  # never raise out of reduce (gap 3)
            doc, code, seats, invalid, not_seated = None, "unparseable", [], [], []
            errors.append(f"selection: {exc}")
        body = selection.strip(turnblock.strip(answer)).strip()
        if delivered and not body:
            # A block with no prose is delivered (gap 4); for a selector the
            # list IS the answer, so only a hermes-turn block alone is signals (I2).
            body = _SIGNALS_ONLY if code == "no_block" else _SEAT_LIST_ONLY
        # The whole lists: the entry shows the first thread.LIST_MAX of each
        # and counts the rest. An empty body writes the NO_TURN stub.
        try:
            thread.append_selection(
                run.id, stage=stage, role=role, body=body, seats=seats,
                not_seated=not_seated, code=code, roster=s["roster"] or None,
            )
        except Exception as exc:  # never raise out of reduce
            errors.append(f"thread: {exc}")
        s["stages"].append(
            {"stage": stage, "role": role, "delivered": delivered, "doc": doc, "code": code}
        )
        # The chair's kept take ratifies (D2 rule 1): resolve and install the
        # committee HERE, before next_phase can mint t01, so the opening round
        # only ever names a seated reviewer. Stage 3's record and thread entry
        # are already written, so resolve sees all three stages and `## committee
        # seated` follows the ratification. Never raises: a resolve that raises
        # (a malformed stage record can), or returns what cannot be installed,
        # seats the default committee with the reason on `error`.
        final: dict = {}
        if stage == 3:
            try:
                resolved = selection.resolve(s["stages"], cast.LIBRARY)
                final = {key: resolved[key] for key in _FINAL_KEYS}
                _apply_selection(s, final)
            except Exception as exc:  # never raise out of reduce
                final = selection.fallback("unparseable")  # reads no stage data
                _apply_selection(s, final)
                errors.append(f"resolve: {exc}")
            try:
                thread.append_seated(
                    run.id,
                    seated=final["seated"],
                    considered=final["considered"],
                    fallback=final["fallback"],
                    roster=s["roster"],
                    # what resolve's caps cut, counted in one line (decision 8)
                    dropped=final["considered_dropped"] + final["invalid_dropped"],
                )
            except Exception as exc:  # never raise out of reduce
                errors.append(f"thread: {exc}")
        return [Reduction(kind="selection", json={
            "stage": stage,
            "role": role,
            "final": stage == 3,
            "delivered": delivered,
            "body": body,
            "parsed": doc is not None,
            "code": code,
            # The same first entries the thread shows, and how many more there
            # were: a 200 KB block must not become a 200 KB reduction.
            "proposed": [
                {key: seat[key] for key in ("role", "name", "title", "rationale")}
                for seat in seats[:thread.LIST_MAX]
            ],
            "proposed_dropped": max(0, len(seats) - thread.LIST_MAX),
            # the stage's notes, cleaned as the thread shows them, and how many
            # entries were invalid, so the card can say who was left out and why
            "not_seated": not_seated[:thread.LIST_MAX],
            "not_seated_dropped": max(0, len(not_seated) - thread.LIST_MAX),
            "invalid_count": len(invalid),
            "error": "; ".join(errors) or None,
            # the master's cap, so the view never guesses it before t01 (D5)
            "cap": s["max_turns"],
            # voice C4, as on a turn
            "take": take,
            "takes": takes,
            "kept": True,
            "voice": metrics,
            "violations": violations,
            "flags": flags,
            # the ratified committee, on the final stage only (C5). Readers take
            # the latest selection reduction with `final: true`; view_data runs
            # in the server process and learns the committee from here alone.
            **final,
        })]

    def _reduce_turn(
        self, run: Run, s: dict, findings: list[Finding]
    ) -> list[Reduction]:
        """One speaker's turn: the thread entry, then the gates."""
        errors: list[str] = []
        role = s["current_role"]  # never None here: `reduce` checked `_lost`
        turn = s["current_turn"]
        answer = _latest_answer(findings)
        discard, metrics, violations, flags = self._grade(run, s, role, answer)
        if discard:
            if role == cast.JUNIOR and s["take"] == 1:
                # What the report-only retakes must leave alone. The same read
                # as their re-check: `read_regular` (O_NOFOLLOW, O_NONBLOCK),
                # never `thread.digest`, which follows a symlink and blocks on
                # a FIFO.
                s["edit_digest"] = _copy_digest(thread.read_regular(s["revised"]))
            return self._discard(run, s, role, answer, metrics, violations, flags, turn)
        answer, take, takes, metrics, violations, flags = self._keep(
            run, s, role, answer, metrics, violations, flags
        )
        body = turnblock.strip(answer)
        # A turn whose whole answer was the block is a DELIVERED turn with no
        # prose -- not a failed one. Only a genuinely absent answer gets the
        # NO_TURN stub (spec 5.2 ties it to "no finding", not "no prose").
        if answer and not body:
            body = _SIGNALS_ONLY

        # An empty body makes `append_turn` write the NO_TURN stub, so a failed
        # turn is visible in the transcript rather than missing from it.
        try:
            thread.append_turn(
                run.id, turn=turn, role=role, body=body, roster=s["roster"] or None
            )
        except Exception as exc:  # never raise out of reduce
            errors.append(f"thread: {exc}")

        block = turnblock.parse(answer)

        # The gates of spec 5.4.
        _apply_block(s, role, block, delivered=bool(answer))

        # `stance` is not a gate -- it steers nothing, so it is not in
        # `_apply_block`. It rides on the turn reduction below and nowhere else:
        # the accumulator that used to sit here duplicated what every turn
        # reduction already carries (role, turn, stance) and had no reader in
        # production code on either side of the seam.

        # --- the independent re-check (spec 7), master-side ---------------
        # The no-trust invariant wants an independent check of an `ok` claim. It
        # cannot live in `verify` (see `reduce`'s docstring), so it rides on the
        # reduction instead: is the revised copy a regular file, and did its
        # sha256 move during THIS turn?
        #
        # RULE: compare against the digest `seed` snapshotted just before the
        # worker ran, never against the original. `ensure_revised` copies once
        # and never again, so after the first delegation the copy differs from
        # the original forever and every later edit -- including one that did
        # nothing -- would read as verified. On the FIRST delegation the
        # snapshot IS the original's digest, which is the check spec 7 describes.
        verified = None
        if role == cast.JUNIOR:
            if s["snapshot_note"]:
                # From this turn's seed: Edit 1's baseline is not doc/00-original.
                errors.append(s["snapshot_note"])
            verified = False
            data = None
            try:
                # ONE read serves the re-check and the doc/tNN snapshot, so the
                # snapshot is exactly the bytes the re-check judged. A symlinked
                # or FIFO revised copy reads as absent (`read_regular`).
                data = thread.read_regular(s["revised"]) if s["revised"] else None
                # `seed` sets this on every junior-IC take 1, and a retake
                # keeps it; there is no fallback, per the RULE above.
                before = s["pre_edit_digest"]
                # An empty `before` is not a digest -- `digest` of a zero-byte
                # file is e3b0c442..., never "" -- it means the snapshot itself
                # failed (`seed`'s OSError path: no copy was made, because the
                # original and doc/00-original were both gone or the write
                # failed). Without the clause, a
                # worker that INVENTED the revised file from nothing hashes to
                # something != "" and is reported verified, inverting the one
                # no-trust check (spec 7).
                verified = bool(
                    before
                    and data is not None
                    and hashlib.sha256(data).hexdigest() != before
                )
            except Exception as exc:  # never raise out of reduce
                errors.append(f"recheck: {exc}")
            # A report-only retake that edited anyway. `verified` above still
            # measures take 1's edit against take 1's snapshot.
            if s["take"] > 1 and s["edit_digest"] and _copy_digest(data) != s["edit_digest"]:
                errors.append("retake modified the revised copy")
            # Every junior-IC turn, delivered or not: an undelivered turn's
            # snapshot is the unchanged copy, which is what the stepper shows.
            try:
                if data is None:
                    errors.append("snapshot: revised copy is not a regular file")
                else:
                    thread.write_snapshot(
                        run.id, thread.snapshot_key(s["artifact"], turn), data
                    )
            except Exception as exc:  # never raise out of reduce
                errors.append(f"snapshot: {exc}")
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
            # Both host paths ride on EVERY turn reduction, the master's own
            # record of what was reviewed and where the edits went. Their
            # readers are committee-eval and the doc/ backfill, which work from
            # reductions alone, and the worker goal names the same paths.
            # `view_data` takes only the file NAME from `artifact` and opens
            # neither: it runs in the server process, possibly in a container
            # where host paths mean nothing, and finds every version under doc/
            # instead. Do not "optimise" these away to the decision reduction
            # alone -- a run that never reached one would lose them.
            "artifact": s["artifact"],
            "revised": s["revised"],
            # The turn cap `seed` resolved: `view_data` runs in the SERVER
            # process, where `_state_by_run` is empty and reading
            # HERMES_COMMITTEE_MAX_TURNS gets THAT process's value. A `hermes serve` started without it rendered
            # "turn 20 of 30" for a run that capped at 20 and used all of it.
            "cap": s["max_turns"],
            # what the speaker ASKED for; whether it was honoured is visible in
            # the run's queue / closed / delegation state.
            "request_floor": bool(block.get("request_floor")),
            "delegate": bool(block.get("delegate")),
            "close": bool(block.get("close")),
            "action": block.get("action"),
            "verified": verified,
            # Always written, null when not applicable: an ABSENT key marks a
            # reduction from before these existed, which the view places by
            # turn order instead.
            "answers_turn": s["answers_turn"],
            "delegated_by_turn": s["delegated_by_turn"],
            # voice C4: which take was kept, how many were dispatched, and what
            # the rules made of it. voice is null for an undelivered take.
            "take": take,
            "takes": takes,
            "kept": True,
            "voice": metrics,
            "violations": violations,
            "flags": flags,
            "error": "; ".join(errors) or None,
        })]

    def _reduce_decision(
        self, run: Run, s: dict, findings: list[Finding], phase: str
    ) -> list[Reduction]:
        """The chair's turn: the verdict, every re-check by name, the disclaimer."""
        errors: list[str] = []
        answer = _latest_answer(findings)
        discard, metrics, violations, flags = self._grade(run, s, cast.CHAIR, answer)
        if discard:
            return self._discard(run, s, cast.CHAIR, answer, metrics, violations, flags, None)
        # A retake that delivered nothing, whether it failed or sent signals
        # only, falls back to the held take: its prose is recorded, unruled.
        retake_failed = metrics is None and bool(s["held"])
        answer, take, takes, metrics, violations, flags = self._keep(
            run, s, cast.CHAIR, answer, metrics, violations, flags
        )
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

        doc = {
            # The verdict goes to a human: the chair's own ticket for this
            # phase (`<run>/decision` or `<run>/decision-take{k}`) is held
            # `needs_human`, so the run ends `done` on accept and `failed` on
            # reject. Everything above is already banked; only the terminal
            # state waits. A failed chair has nothing to rule on and routes
            # nothing.
            "needs_human_ticket_ids": [f"{run.id}/{phase}"] if body else [],
            # the assembled text, so the reduction a reviewer reads carries the
            # re-checks and the disclaimer; empty iff the chair delivered nothing.
            "verdict": text if body else "",
            # read by `is_done`: a chair that delivered nothing ends the run failed
            "delivered": bool(body),
            "rechecks": [dict(check) for check in s["rechecks"]],
            "artifact_intact": intact,
            "dropped_delegation": s["dropped_delegation"],
            "dropped_delegation_turn": s["dropped_delegation_turn"],
            "dropped_floor_requests": list(s["queue"]),
            # Why the meeting stopped. A chair that delivered nothing outranks
            # whatever routed the run here: that IS how this meeting ended, and
            # it is the ending the operator has to act on. The fallback covers a
            # `decision` state that never went through `next_phase` -- reachable
            # only by seeding the phase directly.
            "ended": "chair turn failed" if not body else (s["ended"] or "queue empty"),
            # As on every turn reduction: the master's record for readers of
            # the database; the view takes only the name.
            "artifact": s["artifact"],
            "revised": s["revised"],
            # voice C4, as on a turn: the kept take, how many were dispatched,
            # and what the rules made of it.
            "body": body,
            "take": take,
            "takes": takes,
            "kept": True,
            "voice": metrics,
            "violations": violations,
            "flags": flags,
            "error": "; ".join(errors) or None,
        }
        if retake_failed:
            # The held verdict is on the record, unruled: this phase's retake
            # delivered nothing, whether it failed or sent signals only, so no
            # ticket is held, and the run ends failed like any undelivered decision.
            doc.update(
                needs_human_ticket_ids=[], verdict=text, delivered=False,
                ended="chair retake failed",
            )
        return [Reduction(kind="decision", json=doc)]

    def next_phase(self, run: Run) -> str | None:
        """Who speaks next, then the human's ruling, then None."""
        if run.phase in DECISION_PHASES:
            # A read, never `_state`: a process that never held the meeting must
            # not grow a state here, and it goes to `ruling`, where is_done
            # finds no kept decision and the run ends failed.
            s = self._state_by_run.get(run.id)
            if s and s["retake"]:
                return self._retake(s)
            return "ruling"  # reached once the human has ruled on the held verdict
        if run.phase == "ruling":
            return None  # -> is_done
        s = self._state(run)
        if self._lost(run, s):
            return None  # -> is_done, which has no verdict: the run ends failed
        if s["retake"]:
            # Above delegation, close and the cap: a retake is the same turn
            # said again, and whatever it delegates follows it.
            return self._retake(s)
        if s["selection_next"] <= 3:
            # Selection runs before the meeting and outside it: `_select` never
            # touches the turn counter, `last_speaker` or the cap, so the phase
            # after s3 is t01, numbered exactly as without selection.
            return self._select(s, s["selection_next"])
        # a delegation outranks `close`: an edit the owner asked for still happens,
        # and costs one turn. The cap outranks BOTH, so this can never mint t31.
        if s["delegation"] and s["turn"] <= s["max_turns"]:
            s["pending_action"] = s["delegation"]
            s["delegation"] = None  # consumed exactly once, here
            return self._turn(s, cast.JUNIOR, delegated_by=s["delegation_turn"])
        if s["closed"] or s["turn"] > s["max_turns"]:
            # Mirrors the `or`: an owner that closed is why the meeting stopped,
            # even when the cap would have stopped it on the next hop anyway.
            return self._decision(s, "owner closed" if s["closed"] else "turn cap")
        if s["last_speaker"] != cast.OWNER:
            # the owner answers every reviewer; `current_turn` is still that
            # reviewer's when the argument is evaluated.
            return self._turn(s, cast.OWNER, answers=s["current_turn"])
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
