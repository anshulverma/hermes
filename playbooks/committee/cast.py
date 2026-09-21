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
exactly two runtime-variable strings. Clip those two -- the charge to
``CHARGE_MAX``, a delegated action to ``turnblock.ACTION_MAX`` -- and the whole
thing lands around 2400 characters against a 3600 budget. The assembled string
is never clipped from the end, which is what keeps the read-only guardrail and
the completion condition in every goal; ``GOAL_MAX`` and the unit test are what
keep that honest.

Stdlib-only.
"""
from __future__ import annotations

from playbooks.committee import turnblock as _turnblock

# Role keys the state machine branches on.
OWNER = "owner"
JUNIOR = "junior_ic"

# The chair appears twice: as a reviewer under their own role, and as the author
# of the decision under the sentinel key. `persona` maps the sentinel back.
CHAIR_ROLE = "senior_director"
CHAIR = "chair"

# The charge comes from `--goals` and is operator-supplied, so it is bounded.
CHARGE_MAX = 400

# The whole goal's ceiling. Claude's `/goal` accepts about 4000 characters and
# the adapter appends the driver command inside that allowance.
GOAL_MAX = 3600

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
        "altitude": "company — three orgs and a year out.",
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
        "stake": "her team's commitments this half are already signed.",
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
        "style": "enumerates; asks for dates and names.",
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
        "style": (
            "narrative; draws the boundary and asks where the proposal sits on "
            "it."
        ),
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

_TITLES = {
    "turn": "{name} ({role}) takes the floor in the committee thread",
    "edit": "{name} ({role}) applies the edit the owner delegated",
    "decision": "{name} ({role}) delivers the committee decision",
}


def persona(role: str) -> dict:
    """The nine-field persona for a role.

    The ``chair`` sentinel resolves to the chairing persona, so the decision
    ticket is built with a name and a title rather than with a sentinel. An
    unknown role raises ``KeyError`` -- a typo in a role key should stop a run,
    not silently hand a worker somebody else's brief.
    """
    return CAST[CHAIR_ROLE if role == CHAIR else role]


def brief(role: str) -> str:
    """The persona block that opens every goal.

    Labelled lines rather than sentences: the fields are written as fragments
    ("wants a launch she can tell a story about"), and stitching them into prose
    produces grammar that reads as machine-written.
    """
    p = persona(role)
    return (
        f"You are {p['name']}, {p['title']}.\n"
        f"altitude: {p['altitude']}\n"
        f"goal: {p['goal']}\n"
        f"ambition: {p['ambition']}\n"
        f"stake: {p['stake']}\n"
        f"lens: {p['lens']}\n"
        f"style: {p['style']}"
    )


def title(role: str, kind: str) -> str:
    """The ticket payload's one-line title, for a turn, an edit or the decision.

    The parenthetical is the role as the state machine knows it, so the chair's
    decision ticket reads ``(chair)`` even though the name comes from the
    ``senior_director`` persona.

    An unknown ``kind`` raises ``KeyError``, like ``persona``: a fallback to
    ``turn`` would title the DECISION ticket "takes the floor".
    """
    return _TITLES[kind].format(name=persona(role)["name"], role=role)


# --- the goal ---------------------------------------------------------------
#
# The goal string is the only channel to a worker: the adapter renders
# `goal_envelope.goal` into argv and the ticket payload never travels. So the
# goal carries its material -- who you are, the charge, the two paths, whose
# floor it is, the completion condition -- and the two runtime-variable strings
# are the only ones bounded. Nothing clips the assembled string from the end,
# which is what keeps the guardrail and the completion condition intact.

_GUARDRAIL = (
    "This review lands nothing, submits nothing and touches no repository. "
    "Read the artifact and the thread, and write no file at all."
)

_GUARDRAIL_EDIT = (
    "This review lands nothing, submits nothing and touches no repository. "
    "The revised copy named above is the only file you may write: leave every "
    "other file, the original artifact included, exactly as you found it."
)

_FLOOR_OWNER = (
    "You wrote this proposal and you are accountable for it. Answer the member "
    "who spoke last, directly and in your own voice: concede what their "
    "argument earns and defend what it does not. You make no edits yourself — "
    "an edit is something you delegate."
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
    "Done when: {revised} carries the delegated change and your answer states "
    "in one line what you changed."
)

_DONE_DECISION = (
    "Done when: your answer is the committee's decision — approve / approve "
    "with changes / do not approve — with the reasons, and states that this "
    "verdict is a simulation, not an approval."
)


def _clip(text: str | None, limit: int) -> str:
    """One line of at most ``limit`` characters, ellipsised when cut."""
    line = " ".join(str(text or "").split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def goal(
    role: str,
    *,
    charge: str,
    artifact: str,
    thread: str,
    revised: str,
    action: str | None = None,
) -> str:
    """The whole goal string handed to one worker.

    Three shapes: the chair's decision, the junior IC's edit, and the turn a
    reviewer or the owner takes. Only the charge and a delegated action are
    bounded; everything else is fixed prose, so the assembled goal has a known
    size and the unit test holds it under ``GOAL_MAX``.
    """
    charge = _clip(charge, CHARGE_MAX)

    if role == CHAIR:
        return (
            f"{brief(CHAIR)}\n\n"
            "You chair this proposal review committee. The review is over and "
            "the decision is yours to write.\n\n"
            f"The charge: {charge}\n"
            f"The artifact reviewed: {artifact}\n"
            "The revised copy, which exists only if the committee delegated an "
            f"edit: {revised}\n"
            f"The whole thread: {thread}\n\n"
            # No "weigh what was said, name who is owed an answer, say what
            # would change your mind": that is a review procedure, and spec 9
            # puts methodology behind HERMES_COMMITTEE_DRIVER. The two carve-outs
            # (the junior IC's required output, `lens`) do not cover the chair,
            # and _DONE_DECISION already states the output required.
            "Read the thread end to end and rule on the charge.\n\n"
            f"{_GUARDRAIL}\n\n"
            f"{_DONE_DECISION}"
        )

    if role == JUNIOR:
        # The state machine only mints a junior-IC turn out of a delegation that
        # carried an action, so an empty one means the caller is wrong -- say so
        # rather than dispatching a worker with nothing to do.
        if not str(action or "").strip():
            raise ValueError("a junior_ic goal needs the delegated action")
        return (
            f"{brief(JUNIOR)}\n\n"
            "You support the owner of a proposal under committee review, and "
            "you speak only when the owner delegates something to you.\n\n"
            f"The charge: {charge}\n"
            f"The original artifact, which stays untouched: {artifact}\n"
            f"The revised copy you edit: {revised}\n"
            f"The thread the request came out of: {thread}\n\n"
            "The owner delegated this to you: "
            f"{_clip(action, _turnblock.ACTION_MAX)}\n\n"
            f"{_GUARDRAIL_EDIT}\n\n"
            f"{_DONE_EDIT.format(revised=revised)}"
        )

    floor = _FLOOR_OWNER if role == OWNER else _FLOOR_REVIEWER
    instruction = _turnblock.instruction(owner=role == OWNER).strip()
    return (
        f"{brief(role)}\n\n"
        "You are in a proposal review committee and it is your floor.\n\n"
        f"The charge: {charge}\n"
        f"The artifact under review: {artifact}\n"
        f"The thread: {thread}\n\n"
        "The thread is one single-threaded channel: one speaker at a time, "
        "appended in order. Your answer becomes the next entry -- Hermes "
        "appends it for you. Read the artifact and the thread first.\n\n"
        f"{floor}\n\n"
        f"{_GUARDRAIL}\n\n"
        f"{instruction}\n\n"
        f"{_DONE_TURN}"
    )
