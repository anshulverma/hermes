"""The nine committee personas, and the goal string each member is handed.

A persona is material, not method. DESIGN §8 makes Hermes a goal dispatcher
rather than a prompt templater, so a brief here says who someone is, how far up
they read a problem, and what they want -- for the company and for themselves --
and then stops. *How* to review is the driver's business
(``HERMES_COMMITTEE_DRIVER``, unset by default). Two carve-outs are task
definition rather than method: the junior IC's goal states the output required
of it, never how to make the edit, and ``lens`` names what a persona notices,
never a procedure. If either starts reading like steps, it belongs in the
driver.

``ambition`` is load-bearing. A reviewer who wants something for themselves
argues differently from a neutral critic, and that difference is what makes a
transcript worth reading.

No goal-budget machinery. Research divides one budget between an unbounded,
runtime-sized set of material blocks; a committee goal has a fixed shape with
three runtime-variable strings. Clip those three -- the charge to
``CHARGE_MAX``, a delegated action to ``turnblock.ACTION_MAX``, a retake note to
``voice.RETAKE_NOTE_MAX`` -- and the largest shape, the owner's retake naming
its last take and offering a 1:1 pause, lands around 3570 characters against a
3600 budget. The assembled string is never clipped from the end, which is what
keeps the read-only guardrail and the completion condition in every goal;
``GOAL_MAX`` and the unit test are what keep that honest.

Stdlib-only.
"""
from __future__ import annotations

from playbooks.committee import turnblock as _turnblock
from playbooks.committee import voice as _voice

# Role keys the state machine branches on.
OWNER = "owner"
JUNIOR = "junior_ic"
# The owner's manager: with the owner, the only possible host of a 1:1.
MANAGER = "manager"

# The chair appears twice: as a reviewer under their own role, and as the author
# of the decision under the sentinel key. `persona` maps the sentinel back.
CHAIR_ROLE = "senior_director"
CHAIR = "chair"

# The charge comes from `--goals` and is operator-supplied, so it is bounded.
CHARGE_MAX = 400

# The whole goal's ceiling. Claude's `/goal` accepts about 4000 characters and
# the adapter appends the driver command inside that allowance.
GOAL_MAX = 3600

# A 1:1 topic rides in every exchange goal and its title, so it is bounded like
# the charge. The playbook clips it at scheduling too.
TOPIC_MAX = 160

CAST: dict[str, dict] = {
    "owner": {
        "role": "owner",
        "name": "Maya Okonkwo",
        "title": "Staff Engineer & proposal owner",
        "altitude": "the proposal, end to end.",
        "goal": (
            "get a clear decision, and a better proposal than the one she "
            "walked in with."
        ),
        "ambition": (
            "to be trusted to lead the next thing this size without justifying "
            "it twice."
        ),
        "stake": (
            "she wrote this; a vague outcome leaves months of her team's "
            "roadmap undecided."
        ),
        "lens": (
            "does each objection actually change the design; what can be "
            "conceded cheaply; what must be defended."
        ),
        "style": (
            "direct; concedes fast on small things, digs in with evidence on "
            "the load-bearing claim."
        ),
    },
    "senior_director": {
        "role": "senior_director",
        "name": "Dana Whitfield",
        "title": "Senior Director of Engineering",
        "altitude": "company: three orgs and a year out.",
        "goal": (
            "make sure this is the right bet for the company, not merely a "
            "good idea."
        ),
        "ambition": (
            "wants their org's bet to be the one the company standardises on."
        ),
        "stake": "will be asked in a review of their own why this was funded.",
        "lens": (
            "who else is already doing this; headcount cost; whether it "
            "survives a reorg; who outside this room has to say yes."
        ),
        "style": (
            "asks two questions and stops talking; the second one is the real "
            "one."
        ),
    },
    "manager": {
        "role": "manager",
        "name": "Ruth Delgado",
        "title": "Engineering Manager",
        "altitude": "the team, this half.",
        "goal": "know who does this work and what it displaces.",
        "ambition": (
            "wants it staffed without losing her two strongest engineers to it."
        ),
        "stake": (
            "manages Maya, the proposal owner; her team's commitments this "
            "half are already signed."
        ),
        "lens": (
            "capacity, on-call load, single points of failure, what slips."
        ),
        "style": "concrete and unsentimental; talks in weeks and names.",
    },
    "tpm": {
        "role": "tpm",
        "name": "Sam Iyer",
        "title": "Technical Program Manager",
        "altitude": "across teams, quarter by quarter.",
        "goal": "find the dependency that is not written down.",
        "ambition": "wants a plan they can track, not a narrative.",
        "stake": "owns the schedule this will be plotted on.",
        "lens": (
            "sequencing, external dependencies, what blocks what, the risk "
            "with no owner."
        ),
        "style": "asks for dates and names; one question per risk.",
    },
    "pm": {
        "role": "pm",
        "name": "Elena Vargas",
        "title": "Product Manager",
        "altitude": "the user and the market.",
        "goal": "keep the thing tied to a user problem worth solving.",
        "ambition": "wants a launch she can tell a story about.",
        "stake": "her roadmap promised something adjacent to this.",
        "lens": (
            "who asked for it, what gets cut first, how success reads to "
            "someone outside."
        ),
        "style": (
            "reframes in user language; suspicious of internal-only "
            "justifications."
        ),
    },
    "tl": {
        "role": "tl",
        "name": "Marcus Feld",
        "title": "Tech Lead",
        "altitude": "the system, over two years.",
        "goal": "keep the architecture coherent as this lands.",
        "ambition": (
            "wants the migration he already started to not be orphaned by this."
        ),
        "stake": "he will maintain whatever this becomes.",
        "lens": (
            "how it fits what exists, what it duplicates, migration cost, what "
            "becomes legacy on day one."
        ),
        "style": "draws the boundary and asks where the proposal sits on it.",
    },
    "staff_ic": {
        "role": "staff_ic",
        "name": "Priya Raman",
        "title": "Staff Engineer",
        "altitude": "the mechanism.",
        "goal": "find the assumption the document does not know it is making.",
        "ambition": (
            "wants to be the person whose objection everyone remembers was "
            "right."
        ),
        "stake": "professional credibility rests on catching what others miss.",
        "lens": (
            "failure modes, edge cases, behaviour under load and partial "
            "failure, claims asserted without support."
        ),
        "style": "socratic, precise, quotes the document back.",
    },
    "data_scientist": {
        "role": "data_scientist",
        "name": "Tobias Lin",
        "title": "Data Scientist",
        "altitude": "the evidence.",
        "goal": "check the numbers support the conclusion drawn from them.",
        "ambition": (
            "wants measurement designed in now rather than retrofitted after "
            "launch."
        ),
        "stake": "will be asked to prove this worked.",
        "lens": (
            "baseline, effect size, confounders, whether the metric measures "
            "the thing claimed."
        ),
        "style": "numeric; pedantic about definitions.",
    },
    "junior_ic": {
        "role": "junior_ic",
        "name": "Alex Moreau",
        "title": "Software Engineer",
        "altitude": "the specific change in front of them.",
        "goal": (
            "execute exactly what the owner delegates, accurately, without "
            "freelancing."
        ),
        "ambition": "wants to be trusted with bigger pieces.",
        "stake": "an edit that misses the point wastes the committee's time.",
        "lens": (
            "exactly what was asked; whether the change says what the owner "
            "meant."
        ),
        "style": "brief; confirms what changed in one line.",
    },
}

# The opening round, and the only roles that may ever join the floor queue. The
# owner is excluded because it answers every reviewer anyway; the junior IC is
# excluded because it is reachable only by delegation (§4).
SENIORITY: tuple[str, ...] = (
    "senior_director",
    "manager",
    "tpm",
    "pm",
    "tl",
    "staff_ic",
    "data_scientist",
)

# The seat pool the three selectors draw reviewers from (selection C2). Five are
# CAST's own reviewers, by reference, so a library seat is the persona the
# legacy cast already has and voice's styles hold for both. Treat every entry
# as read-only: a seat record is always a new dict built from one. The fixed
# seats (owner, senior_director, manager, junior_ic) are always seated and so
# never selectable. The four new personas carry the eight brief fields and no
# `role` key, because the slug is the role.
LIBRARY: dict[str, dict] = {
    "tpm": CAST["tpm"],
    "pm": CAST["pm"],
    "tl": CAST["tl"],
    "staff_ic": CAST["staff_ic"],
    "data_scientist": CAST["data_scientist"],
    "security": {
        "name": "Nadia Haddad",
        "title": "Security Engineer",
        "altitude": "the trust boundary, and who can cross it.",
        "goal": "know what this exposes, to whom, and who signs it off.",
        "ambition": "wants security designed in now, not bolted on at launch review.",
        "stake": "her team signs the security review this must pass before it ships.",
        "lens": (
            "trust boundaries, credentials and secrets, blast radius, who can "
            "reach what."
        ),
        "style": "asks what an attacker tries first; one threat per question.",
    },
    "sre": {
        "name": "Owen Brennan",
        "title": "Site Reliability Engineer, on-call",
        "altitude": "production, at three in the morning.",
        "goal": "know how this fails, how anyone notices, and who gets paged.",
        "ambition": "wants the runbook and the alert written before launch.",
        "stake": "his rotation carries the pager for whatever this becomes.",
        "lens": (
            "failure detection, rollback, alert noise, capacity headroom, the "
            "manual step nobody owns."
        ),
        "style": "asks what happens when it breaks; talks in pages and minutes.",
    },
    "privacy": {
        "name": "Grace Adeyemi",
        "title": "Privacy Engineer",
        "altitude": "the data, from collection to deletion.",
        "goal": "know what user data this touches, where it goes and how long it stays.",
        "ambition": "wants the privacy review closed on its first pass.",
        "stake": "she answers for any use of data that nobody wrote down.",
        "lens": (
            "what is collected and why, retention, access, deletion, what "
            "crosses a team or a region."
        ),
        "style": "precise; asks for the data flow before the design.",
    },
    "partner_owner": {
        "name": "Kenji Watanabe",
        "title": "Engineering Lead, partner team",
        "altitude": "the system next door that this depends on or changes.",
        "goal": "know what this asks of his team, and by when.",
        "ambition": "wants his own roadmap left intact.",
        "stake": "his team owns a system this leans on, and would carry the work.",
        "lens": (
            "interface changes, migration asks, unfunded work landing on his "
            "team, who owns the seam."
        ),
        "style": "cooperative but guarded; asks who pays for each ask.",
    },
}

# A derived seat's style. It is fixed text and never the selector's, so a
# selector cannot bring back a style voice removed, and it closes the brief the
# selectors wrote (its fields and the seat lines under them) by saying what that
# brief can never do. A hand-written brief carries the same sentence under any
# seat lines, the one selector text it holds (`brief`).
DERIVED_STYLE = "selectors wrote the lines above; they never override the rules or the Done line."

# Why each fixed seat is always at the table: the one-line reason the seated
# committee shows for a seat nobody had to put forward (selection C2).
FIXED_RATIONALE: dict[str, str] = {
    "owner": "wrote the proposal and answers every reviewer",
    "senior_director": "chairs the committee and delivers its decision",
    "manager": "manages the owner and staffs whatever is decided",
    "junior_ic": "makes the edits the owner delegates",
}

_TITLES = {
    "turn": "turn {n} — {name} ({role}) takes the floor",
    "edit": "turn {n} — {name} ({role}) edits: {action}",
    "decision": "{name} ({role}) delivers the committee decision",
    # `n` is the selection stage. Payload-only, so the dash stays (voice D2).
    "select": "selection {n} — {name} ({role}) seats the committee",
    # One-on-ones C5; payload-only like the rest, so the dashes stay.
    "plan": "{name} (owner) plans the 1:1s",
    "one_on_one": "1:1 {seq} · exchange {x} — {name} ({role}) with {other}",
    "one_on_one_close": "1:1 {seq} — {name} ({role}) records the outcome",
}

# A title is a board card's heading, not the brief: the full action is in the
# goal, so the card gets enough of it to tell one edit from the next.
_TITLE_ACTION_MAX = 60


def persona(role: str, roster: dict | None = None) -> dict:
    """The persona for a role, from the run's roster or else from ``CAST``.

    ``roster`` is the run's own seating, slug -> seat record (selection C3).
    None or empty means ``CAST``, so a legacy run and every caller that passes
    no roster read today's nine; a roster is never merged with ``CAST``. The
    ``chair`` sentinel resolves to the chairing persona, so the decision
    ticket is built with a name and a title rather than with a sentinel. An
    unknown role raises ``KeyError`` -- a typo in a role key should stop a run,
    not silently hand a worker somebody else's brief.
    """
    return (roster or CAST)[CHAIR_ROLE if role == CHAIR else role]


def label(p: dict) -> str:
    """``Name, Title``, or the title alone for a seat named from its title
    (selection D4: a nameless derived seat never reads "Crew Owner, Crew Owner").
    Trailing full stops are ignored, and a name ending "…" is the title clipped."""
    name, title = p["name"], p["title"]
    stem = name.removesuffix("…").rstrip(". ")
    same = name.rstrip(". ") == title.rstrip(". ") or (
        name.endswith("…") and bool(stem) and title.startswith(stem))
    return title if same else f"{name}, {title}"


def brief(role: str, roster: dict | None = None, speaks_for=()) -> str:
    """The persona block that opens every goal.

    Labelled lines rather than sentences: the fields are written as fragments
    ("wants a launch she can tell a story about"), and stitching them into prose
    produces grammar that reads as machine-written. The seat lines
    (``_seat_lines``) sit above the style line, so a derived seat's
    ``DERIVED_STYLE`` covers them too.
    """
    p = persona(role, roster)
    return (
        f"You are {label(p)}.\n"
        f"altitude: {p['altitude']}\n"
        f"goal: {p['goal']}\n"
        f"ambition: {p['ambition']}\n"
        f"stake: {p['stake']}\n"
        f"lens: {p['lens']}\n"
        f"{_seat_lines(p, speaks_for)}"
        f"style: {p['style']}"
    )


def title(
    role: str,
    kind: str,
    *,
    turn: int,
    action: str | None = None,
    take: int = 1,
    roster: dict | None = None,
    other: str | None = None,
    seq: int | None = None,
    exchange: int | None = None,
) -> str:
    """The ticket payload's one-line title, for every kind of ticket.

    The parenthetical is the role as the state machine knows it, so the chair's
    decision ticket reads ``(chair)`` even though the name comes from the
    ``senior_director`` persona. ``turn`` has no default because a title that
    says "turn 0" is wrong. The decision is not a turn, so its title ignores it.
    A retake says which take it is; the payload keys are frozen, so the title
    and the goal are the only channels a retake has. Names resolve through the
    run's ``roster`` (None means ``CAST``). A 1:1 title names its ``seq``, the
    ``exchange`` and ``other``: the other member's role, resolved through the
    same roster, since a library or derived seat is not in ``CAST``.

    An unknown ``kind`` raises ``KeyError``, like ``persona``: a fallback to
    ``turn`` would title the DECISION ticket "takes the floor".
    """
    text = _TITLES[kind].format(
        name=persona(role, roster)["name"], role=role, n=turn,
        action=clip(action, _TITLE_ACTION_MAX),
        other=persona(other, roster)["name"] if other else "",
        seq=seq, x=exchange,
    )
    return f"{text} (take {take})" if take > 1 else text


# --- the goal ---------------------------------------------------------------
#
# The goal string is the only channel to a worker: the adapter renders
# `goal_envelope.goal` into argv and the ticket payload never travels. So the
# goal carries its material -- who you are, the charge, the two paths, whose
# floor it is, the completion condition -- and the three runtime-variable
# strings (the charge, a delegated action, a retake note) are the only ones
# bounded. Nothing clips the assembled string from the end, which is what keeps
# the guardrail and the completion condition intact.

_GUARDRAIL = (
    "This review lands nothing, submits nothing and touches no repository. "
    "Read the artifact and the thread, and write no file at all."
)

_GUARDRAIL_EDIT = (
    "This review lands nothing, submits nothing and touches no repository. "
    "The revised copy named above is the only file you may write: leave every "
    "other file, the original artifact included, exactly as you found it. That "
    "copy is already a byte copy of the original: change only what was "
    "delegated and leave the rest of it alone."
)

# The first live run: the chair inspected the REPOSITORY file, found it
# unchanged, called six landed delegations "zero bytes" and ruled partly against
# the proposal on that reading. All six had landed — the revised copy went
# 11,397 -> 19,100 bytes and every re-check reported APPLIED.
#
# One sentence to EVERY speaker, not just the chair, because the chair did not
# mint that reading: the thread has it minted by reviewers five turns earlier
# and the chair citing them. The one persona that got it right — "this review
# writes only the revised copy" — is the one whose goal already names the
# revised copy, and the reviewer and owner goals never mention it at all.
#
# An unchanged original is criterion 6, the guarantee _GUARDRAIL exists to keep.
# But the guardrail tells a speaker what IT may not do; it does not say how to
# read a repository nobody was allowed to touch. Say that outright, before
# anyone infers a broken edit mechanism from a working one.
#
# Present tense on purpose. "every delegated edit LANDED" is a claim about THIS
# run that the goal cannot know: `_reduce_decision` appends `DID NOT APPLY` for
# a re-check that failed, and it appends it UNDER the chair's prose, so the
# chair is told the edits landed while the footer beneath its own verdict says
# one did not. That is the same defect as the one this paragraph fixes, pointed
# the other way.
_UNCHANGED_ORIGINAL = (
    "The original artifact is never modified: every delegated edit lands in a "
    "separate revised copy, and that is by design: an unchanged original is "
    "the guarantee holding, not an edit that failed. What this committee "
    "produces is a recommendation plus that copy, not a landed change."
)

_FLOOR_OWNER = (
    "You wrote this proposal and you are accountable for it. Answer the member "
    "who spoke last, directly and in your own voice: concede what their "
    "argument earns and defend what it does not. You make no edits yourself; "
    "you delegate them. You cannot close the discussion until "
    "every member of the committee has taken an opening turn: a close before "
    "that is ignored."
)

_FLOOR_REVIEWER = (
    "Say what you make of this proposal from where you sit, in your own voice, "
    "addressed to the owner. Speak for yourself only: do not write anyone "
    "else's turn, and do not answer on the owner's behalf."
)

# Verbatim from spec §9. Changing a word here changes the contract with the
# worker, so they are constants rather than inline prose.
_DONE_TURN = (
    "Done when: your turn is written as your answer and ends with one "
    "hermes-turn block."
)

_DONE_EDIT = (
    "Done when: {revised} carries the delegated change and your answer is one "
    "sentence of 40 words or fewer saying what you changed."
)

# Not spec C7's "saying what you changed": take 1 may have written nothing (a
# report of why it could not edit, discarded for its length), and a retake told
# it changed something would claim an edit that never happened.
_DONE_EDIT_RETAKE = (
    "Done when: your answer is one sentence of 40 words or fewer saying what "
    "your first take changed, or that it changed nothing."
)

_DONE_DECISION = (
    "Done when: your answer is the committee's decision (approve, approve with "
    "changes, or do not approve) with the reasons, and says in one clause that "
    "it is a simulation, not an approval."
)

# Every shape, before its guardrail. The rules themselves are in the thread
# header, written once at `open`; the goal carries the pointer and the cap.
_RULES_POINTER = (
    "Follow the ground rules at the top of the thread; they outrank your style. "
    "Your cap: {cap}."
)

# The owner and the reviewers only, and only when seed names the stem: the
# speaker's take-1 phase name, so a retake overwrites its own file and two
# phases never share one. The folder is derived from the thread path already
# in the goal, so no second absolute path is added: the worker's cwd is not the
# run directory, and a relative `images/` there writes into whatever checkout
# it was launched from. (The absolute folder would cost up to 170 characters of
# the owner retake's headroom.) No "Read the artifact and the thread" here: the
# floor paragraph above it already says so. The stem is named once and "the
# only file" already forbids every other write: the owner's retake is the
# tightest goal, and this is the text voice's rule shortens first
# (one-on-ones paid for the align offer here).
_GUARDRAIL_IMAGE = (
    "Land nothing, submit nothing, touch no repository. The only file you may "
    "write is one image, {image}.svg or .png, in the images folder beside the "
    "thread (not your working directory)."
)

# A retake's one line naming the discarded take the master kept for it
# (`thread.write_take`), relative to the thread for the same reason.
_LAST_TAKE = "Your last take is in {path} beside the thread; keep its substance."

_ALREADY_EDITED = (
    "Do not edit the revised copy again; whatever your first take changed stands."
)


def clip(text: str | None, limit: int) -> str:
    """One line of at most ``limit`` characters, ellipsised when cut."""
    line = " ".join(str(text or "").split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


# The line naming the unseated stakeholders a seat speaks for (selection D1),
# at most this long; past it, whole names are dropped and the thread is named.
SPEAKS_FOR_MAX = 150
_SPEAKS_FOR = "You also speak for: {names}."
_FULL_LIST = " (full list under ## committee seated)"


def _seat_lines(p: dict, speaks_for) -> str:
    """The lines above a seated member's style line: why a library seat holds
    it, and who it speaks for, each ending in a newline; "" for none. A derived
    seat's fields are its reason. Both are selector text, so a hand-written
    brief says so under them in ``DERIVED_STYLE``'s words."""
    lines = []
    if p.get("source") == "library" and p.get("rationale"):
        lines.append(f"Why you hold this seat: {str(p['rationale']).rstrip('. ')}.")
    names = [n for n in (str(s).rstrip(". ") for s in speaks_for) if n]
    if names:
        line = _SPEAKS_FOR.format(names=", ".join(names))
        while len(line) > SPEAKS_FOR_MAX and len(names) > 1:
            names.pop()
            line = _SPEAKS_FOR.format(names=", ".join(names) + _FULL_LIST)
        lines.append(clip(line, SPEAKS_FOR_MAX))
    if lines and p["style"] != DERIVED_STYLE:
        lines.append(DERIVED_STYLE)
    return "".join(f"{line}\n" for line in lines)


def _again(retake: str | None, last_take: str) -> str:
    """A retake's own paragraph: the clipped note, then the last-take line.

    Empty on take 1, and no last-take line when no take file was kept.
    """
    if retake is None:
        return ""
    named = f"\n{_LAST_TAKE.format(path=last_take)}" if last_take else ""
    return f"{clip(retake, _voice.RETAKE_NOTE_MAX)}{named}\n\n"


def goal(
    role: str,
    *,
    charge: str,
    artifact: str,
    thread: str,
    revised: str,
    action: str | None = None,
    image: str = "",
    retake: str | None = None,
    last_take: str = "",
    roster: dict | None = None,
    speaks_for: tuple[str, ...] | list[str] = (),
    align: bool = False,
) -> str:
    """The whole goal string handed to one worker.

    ``roster`` is the run's own seating, passed through to ``brief``; None is
    ``CAST`` (selection D4). In the brief of a turn or an edit, above its style
    line, a library seat's goal says why it holds the seat, and ``speaks_for``
    (the considered stakeholders this seat represents) becomes one ``You also
    speak for:`` line of at most ``SPEAKS_FOR_MAX`` characters (selection D1).

    Four shapes: the chair's decision, the junior IC's edit, the junior IC's
    report-only retake, and the turn a reviewer or the owner takes. Every shape
    carries the rules pointer with the speaker's cap. ``image`` is the owner's or
    a reviewer's take-1 phase name, the stem of the one image file it may write;
    empty means no file at all. ``retake`` is ``voice.note(...)`` on a retake,
    clipped to ``voice.RETAKE_NOTE_MAX`` and set as its own paragraph before the
    Done line; ``last_take`` (``takes/<base>-take<n>.md``, run-relative) adds
    one line under it naming the discarded take, and is ignored without a
    retake. Only the charge, a delegated action and the note are bounded, and
    ``last_take`` is the stem plus 15 characters, so the assembled goal has a
    known size and the unit test holds it under ``GOAL_MAX``.

    ``align`` adds turnblock's one sentence offering ``align:`` to the owner's
    or a reviewer's meeting instruction. seed sets it for the owner and the
    manager, and only while the run's 1:1 budget can hold a 1:1; the chair's
    and the junior IC's shapes ignore it.
    """
    charge = clip(charge, CHARGE_MAX)
    pointer = _RULES_POINTER.format(cap=_voice.cap_text(role))
    again = _again(retake, last_take)

    if role == CHAIR:
        return (
            f"{brief(CHAIR, roster)}\n\n"
            # The brief above is the senior_director's, and its `style` line --
            # "asks two questions and stops talking" -- is a fine REVIEWER
            # instruction and a terrible chair instruction. `is_done` accepts
            # any non-empty prose as the verdict, so a chair that returned two
            # questions would end the run `done` on a non-decision. One sentence
            # is cheaper than a tenth persona.
            "That brief is how you reviewed this proposal. You chair it too, "
            "and in the chair you rule rather than question. The review is over "
            "and the decision is yours to write.\n\n"
            f"The charge: {charge}\n"
            f"The artifact reviewed: {artifact}\n"
            "The revised copy, which exists only if the committee delegated an "
            f"edit: {revised}\n"
            f"The whole thread: {thread}\n\n"
            # The chair is the one speaker handed the revised copy's path, and
            # the one asked to weigh what is in it.
            f"{_UNCHANGED_ORIGINAL} Judge the delegated edits by the copy "
            "named above.\n\n"
            # No "weigh what was said, name who is owed an answer, say what
            # would change your mind": that is a review procedure, and spec 9
            # puts methodology behind HERMES_COMMITTEE_DRIVER. The two carve-outs
            # (the junior IC's required output, `lens`) do not cover the chair,
            # and _DONE_DECISION already states the output required.
            "Read the thread end to end and rule on the charge.\n\n"
            f"{pointer}\n\n"
            f"{_GUARDRAIL}\n\n"
            f"{again}"
            f"{_DONE_DECISION}"
        )

    if role == JUNIOR:
        # The state machine only mints a junior-IC turn out of a delegation that
        # carried an action, so an empty one means the caller is wrong -- say so
        # rather than dispatching a worker with nothing to do.
        if not str(action or "").strip():
            raise ValueError("a junior_ic goal needs the delegated action")
        head = (
            f"{brief(JUNIOR, roster, speaks_for)}\n\n"
            "You support the owner of a proposal under committee review, and "
            "you speak only when the owner delegates something to you.\n\n"
            f"The charge: {charge}\n"
            f"The original artifact, which stays untouched: {artifact}\n"
            f"The revised copy you edit: {revised}\n"
            f"The thread the request came out of: {thread}\n\n"
            "The owner delegated this to you: "
            f"{clip(action, _turnblock.ACTION_MAX)}\n\n"
            f"{_UNCHANGED_ORIGINAL}\n\n"
        )
        if retake is not None:
            # Report-only: whatever take 1 wrote is already in the copy and
            # its re-check measures that, so this take writes nothing.
            return (
                f"{head}{_ALREADY_EDITED}\n\n{again}{pointer}\n\n"
                f"{_GUARDRAIL}\n\n{_DONE_EDIT_RETAKE}"
            )
        return (
            f"{head}{pointer}\n\n{_GUARDRAIL_EDIT}\n\n"
            f"{_DONE_EDIT.format(revised=revised)}"
        )

    floor = _FLOOR_OWNER if role == OWNER else _FLOOR_REVIEWER
    guardrail = _GUARDRAIL_IMAGE.format(image=image) if image else _GUARDRAIL
    instruction = _turnblock.instruction(owner=role == OWNER, align=align).strip()
    return (
        f"{brief(role, roster, speaks_for)}\n\n"
        "You are in a proposal review committee and it is your floor.\n\n"
        f"The charge: {charge}\n"
        f"The artifact under review: {artifact}\n"
        f"The thread: {thread}\n\n"
        "The thread is one channel: one speaker at a time, "
        "appended in order. Your answer becomes the next entry; Hermes "
        "appends it for you. Read the artifact and the thread first.\n\n"
        f"{floor}\n\n"
        f"{_UNCHANGED_ORIGINAL}\n\n"
        f"{pointer}\n\n"
        f"{guardrail}\n\n"
        f"{instruction}\n\n"
        f"{again}"
        f"{_DONE_TURN}"
    )


# --- the selection goals (selection D7) --------------------------------------
#
# Three stages seat the committee before t01: the owner proposes, her manager
# amends, the chair ratifies. The seat library is in the thread header, written
# once at `open`, so a goal names it and never inlines it. No
# `turnblock.instruction()`: a selector's hermes-turn block is ignored.

_SELECT_FRAMING = (
    "You are seating the committee that will review this proposal. The "
    "meeting has not started. A stakeholder is anyone who builds, runs, "
    "secures, pays for, depends on or is changed by it."
)

_SELECT_DUTY = {
    1: "You go first: propose the committee.",
    2: (
        "Amend the list above yours: keep, add or drop seats. If the thread "
        "holds no usable list above yours, propose one."
    ),
    3: (
        "You ratify: your list is final and the meeting runs with it. In this "
        "seat you decide; you do not question. If the thread holds no usable "
        "list above yours, propose one. Every stakeholder named above ends "
        "seated, or under not_seated with a seated representative."
    ),
}

_SEAT_RULE = (
    "Pick each seat from the seat library in the thread header, or name a "
    "stakeholder the document justifies. The owner, the senior director, the "
    "manager and the junior IC are always seated, so list the 1-10 others in "
    "the block below, each with a one-line rationale. Name every other "
    "stakeholder under not_seated, with the seated role that represents them. "
    "For a seat listed above that you drop, give its role slug as the stakeholder."
)

# Placeholders, not a worked example: a copied "<slug>" fails SLUG_RE and is
# recorded as an invalid entry, where a copied real slug would seat someone.
# The fence reader (voice's) skips a fence indented under a list item, so the
# goal says where the fence lines go.
_SELECT_BLOCK = (
    "End with this block holding your full list, never just the changes. Both "
    "fence lines start at column 0 on their own line, never inside a list item:\n\n"
    "```hermes-selection\n"
    '{"seats": [{"role": "<slug>", "name": "<name>", "title": "<title>", '
    '"stake": "<stake>", "lens": "<lens>", "rationale": "<why>"}],\n'
    ' "not_seated": [{"stakeholder": "<who>", "reason": "<why not>", '
    '"represented_by": "<seated role>"}]}\n'
    "```\n\n"
    # selection.SLUG_RE's rule, pinned against it by the unit test
    "A role is a lowercase slug of 2 to 24 letters, digits and underscores, "
    'starting with a letter. A seat from outside the library also needs a '
    '"title", and may add "altitude", "goal" and "ambition", one line each.'
)

_DONE_SELECT = "Done when: your answer ends with one hermes-selection block."


def select_goal(
    role: str,
    *,
    stage: int,
    charge: str,
    artifact: str,
    thread: str,
    image: str,
    retake: str | None = None,
    last_take: str = "",
) -> str:
    """The goal for selection stage ``stage`` (1-3), handed to a fixed seat.

    D7's order: the brief and the framing, the material, the stage duty, the
    seat rule, the block, the rules pointer and the image guardrail, the retake
    note (with the last-take line, as in ``goal``), the Done line. ``image`` is
    the stage's take-1 phase name (``s1-owner``), the stem of the one image it
    may write; empty (seed found the images folder refused) means no file at
    all, as in ``goal``. No ``roster``: the three selectors are fixed seats in
    ``CAST``. An unknown stage raises ``KeyError``, like an unknown title kind.
    """
    guardrail = _GUARDRAIL_IMAGE.format(image=image) if image else _GUARDRAIL
    # the write-nothing guardrail says "Read the artifact and the thread"; the image one does not
    read = "Read the artifact and the thread first.\n\n" if image else ""
    return (
        f"{brief(role)}\n\n"
        f"{_SELECT_FRAMING}\n\n"
        f"The charge: {clip(charge, CHARGE_MAX)}\n"
        f"The artifact under review: {artifact}\n"
        f"The thread: {thread}\n\n"
        f"{read}"
        f"{_SELECT_DUTY[stage]}\n\n"
        f"{_SEAT_RULE}\n\n"
        f"{_SELECT_BLOCK}\n\n"
        f"{_RULES_POINTER.format(cap=_voice.cap_text(role))}\n\n"
        f"{guardrail}\n\n"
        f"{_again(retake, last_take)}"
        f"{_DONE_SELECT}"
    )


# --- 1:1s: the plan and the exchanges ---------------------------------------
#
# A 1:1 is not speech in the room. Its goals drop the floor text, the meeting
# keys and the unchanged-original paragraph, which keeps the longest of them
# inside GOAL_MAX, and they always carry the write-nothing guardrail, never
# the image one: the images folder is shared with the room, and a 1:1 is
# private. The master grades every 1:1 answer with file images off, so an
# image file a worker wrote anyway is never accepted.

_DONE_PLAN = (
    "Done when: your answer names the 1:1s you want and ends with one "
    "hermes-turn block."
)

_DONE_ONE_ON_ONE = (
    "Done when: your exchange is written as your answer and ends with one "
    "hermes-turn block."
)

_PLAN_DUTY = (
    "Before the opening round you may hold one to three 1:1s, hosted by you or "
    "your manager (`manager`); the seated committee and its role keys are "
    "listed under `## committee seated` in {thread}."
)

# Named once, in the line that says who: every later mention says "the 1:1
# file", because the path is the longest string in the goal.
_FILE_LINE = (
    "Only this 1:1's participants are told about its file, and Hermes appends "
    "your answer to it: {file}"
)


def _undash(text: str | None) -> str:
    """Both long dashes as ``-``: worker text re-entering a goal keeps voice's rule 5."""
    return str(text or "").replace("\u2013", "-").replace("\u2014", "-")


def plan_goal(*, charge: str, artifact: str, thread: str, roster: dict) -> str:
    """The owner's one planning ticket, between selection and the opening round.

    ``roster`` is the run's seated roster; its role keys are the ones a
    ``meet_N`` line may name, and the thread lists them under
    ``## committee seated``.
    """
    pointer = _RULES_POINTER.format(cap=_voice.cap_text(OWNER))
    return (
        f"{brief(OWNER, roster or None)}\n\n"
        f"{_PLAN_DUTY.format(thread=thread)}\n\n"
        f"The charge: {clip(charge, CHARGE_MAX)}\n"
        f"The artifact under review: {artifact}\n"
        f"The thread: {thread}\n\n"
        f"{pointer}\n\n"
        f"{_GUARDRAIL}\n\n"
        f"{_turnblock.plan_instruction().strip()}\n\n"
        f"{_DONE_PLAN}"
    )


def one_on_one_goal(
    role: str,
    *,
    charge: str,
    artifact: str,
    thread: str,
    file: str,
    other: str | None,
    members: list[str],
    topic: str,
    exchange: int | None,
    host: str,
    closing: bool,
    roster: dict,
    retake: str | None = None,
    last_take: str = "",
    speaks_for: tuple[str, ...] | list[str] = (),
) -> str:
    """One exchange of a 1:1, or its host's closing exchange.

    ``role`` speaks. ``members`` are the two who exchange, ``other`` is the
    member ``role`` is talking to (None on a closing exchange), and ``host``
    is the owner or the manager who keeps the outcome. ``file`` is the private
    1:1 file's absolute path. ``exchange`` is the member exchange number
    (1-4), None on a closing exchange; the "4" below is the playbook's
    exchange cap written out, since cast cannot import playbook. ``retake``,
    ``last_take`` and ``speaks_for`` behave as in ``goal``: the clipped note
    and the line naming the kept take are their own paragraph before the Done
    line, and a seated member's brief says who it speaks for.
    """
    roster = roster or None

    def name(seat: str) -> str:
        return persona(seat, roster)["name"]

    subject = clip(_undash(topic), TOPIC_MAX)
    if closing:
        who = (
            f"You host a private 1:1 on: {subject}. This is the closing "
            "exchange: the members have finished."
        )
        duty = (
            f"You called this 1:1 between {name(members[0])} and "
            f"{name(members[1])}. Read the 1:1 file and record the outcome: "
            "the room reads only your `agreed` and `still_open`."
        )
    else:
        if role == host:
            hosted = "which you host"
        elif other == host:
            hosted = "who hosts it"
        else:
            hosted = f"hosted by {name(host)}"
        who = (
            f"You are in a private 1:1 with {name(other)}, {hosted}, on: "
            f"{subject}. This is exchange {exchange} of at most 4."
        )
        if role == host:
            duty = (
                f"Read the 1:1 file, answer {name(other)} and keep `agreed` and "
                "`still_open` current: the room reads only those."
            )
        elif exchange == 1:
            duty = (
                "State your position and what would align you. The 1:1 file is "
                "empty until your exchange, which opens it, so do not read it."
            )
        else:
            duty = (
                "State your position and what would align you. Read the 1:1 "
                "file first."
            )
    instruction = _turnblock.one_on_one_instruction(
        host=role == host, owner=role == OWNER, closing=closing,
    ).strip()
    return (
        f"{brief(role, roster, speaks_for)}\n\n"
        f"{who} {_FILE_LINE.format(file=file)}\n\n"
        f"The charge: {clip(charge, CHARGE_MAX)}\n"
        f"The artifact under review: {artifact}\n"
        f"The thread: {thread} (its header holds the ground rules)\n\n"
        f"{duty}\n\n"
        f"{_RULES_POINTER.format(cap=_voice.cap_text(role))}\n\n"
        f"{_GUARDRAIL}\n\n"
        f"{instruction}\n\n"
        f"{_again(retake, last_take)}"
        f"{_DONE_ONE_ON_ONE}"
    )
