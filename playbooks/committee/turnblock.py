"""One turn's control signals, carried inside the speaker's prose.

The transport hands the master exactly one thing from a worker: its final text,
under ``answer``. A committee turn has to say more than its prose does --
whether the speaker wants the floor again, whether the owner is delegating an
edit or closing the discussion -- and there is no second channel to say it on.

Reading it out of the prose does not work, for the reason
``playbooks/research/verdict.py`` gives at length: a reviewer writes "I'd close
on this" and "delegate that to someone" as ordinary English, and a control
signal scraped out of ordinary English steers the meeting wrong. So the speaker
is asked for a block with its own tag instead. That is unambiguous both ways:
present and parseable, or absent. **Absent stays absent** -- a key that was not
written is not in the returned dict, never defaulted to False. ``next_phase``
happens to read "unstated" and "no" alike, but the reduction records which one
was said, and a reader of the transcript can tell them apart.

Unlike ``verdict.py``, which ``json.loads`` its fence body, this body is
line-oriented ``key: value``. Every value is yes/no or one line of English;
asking an agent for JSON here buys nothing and costs a whole class of quoting
failures.

This module is a pure parser. It knows nothing about roles: ``delegate`` and
``close`` are owner-only and ``request_floor`` is reviewer-only, but those
gates live in ``reduce``, which knows who is speaking. ``parse`` reports what
the block literally said.

Stdlib-only.
"""
from __future__ import annotations

import re

# The info string on the fence. Deliberately not `yaml` or `ini`: an agent
# writes plenty of ordinary key/value blocks, and only this tag means "these
# are my control signals".
FENCE_TAG = "hermes-turn"

# The closed vocabulary. Anything else in the block is dropped -- an agent
# inventing a key must not become a signal nobody defined.
ACTION = "action"
STANCE = "stance"
# The five meeting keys, then the 1:1 keys: a member's `aligned`, a host's
# `agreed` and `still_open`, a meeting turn's `align` and the plan's
# `meet_1..3`. Which speaker may use which is reduce's gate, not the parser's.
KEYS: tuple[str, ...] = (
    "request_floor", "delegate", ACTION, "close", STANCE,
    "aligned", "agreed", "still_open", "align", "meet_1", "meet_2", "meet_3",
)

# An action rides in a goal that shares a hard character budget with the
# persona and both paths, and it names one edit. One line is the whole point.
ACTION_MAX = 200

# A stance is one line of where a speaker currently stands. Same budget as an
# action for the same reason: it is rendered per persona, not read as a page.
STANCE_MAX = 200

# `align` and `meet_N` carry two role keys and a topic (see `pair`); `agreed`
# and `still_open` are a 1:1 host's outcome. Each is one line the room reads
# back, so each gets the same one-line cap.
PAIR_MAX = 200
OUTCOME_MAX = 200

# The free-text keys and the cap each one is clipped to. The rest are yes/no.
_TEXT: dict[str, int] = {
    ACTION: ACTION_MAX,
    STANCE: STANCE_MAX,
    "agreed": OUTCOME_MAX,
    "still_open": OUTCOME_MAX,
    "align": PAIR_MAX,
    "meet_1": PAIR_MAX,
    "meet_2": PAIR_MAX,
    "meet_3": PAIR_MAX,
}

# The keys whose value is yes/no. DERIVED from KEYS, not a second list: a sixth
# signal added to KEYS alone would be declared vocabulary that `_one` silently
# drops, with a green suite either way.
_FLAGS = tuple(key for key in KEYS if key not in _TEXT)

_BLOCK_RE = re.compile(
    r"```[ \t]*" + re.escape(FENCE_TAG) + r"[ \t]*\n(.*?)\n?```",
    re.DOTALL | re.IGNORECASE,
)


def parse(answer: str | None) -> dict:
    """The signals an answer carries, or {} when it carries none.

    The last block wins: an agent that restates its block has settled on the
    later one.
    """
    if not isinstance(answer, str) or not answer:
        return {}

    blocks = _BLOCK_RE.findall(answer)
    if not blocks:
        return {}
    return _one(blocks[-1])


def _one(raw: str) -> dict:
    """One block body as signals. Only known, well-formed lines survive.

    A flag value that is neither yes nor no is dropped, not read as no: an
    agent that wrote `request_floor: maybe` did not decline the floor, and
    recording a decline it never made is the failure mode this whole module
    exists to avoid.

    Every non-printable character in a value (a control such as NUL, an
    invisible or bidi mark, a lone surrogate) becomes a space first. Every text
    key passes here on its way into a goal, a file or the view, and a NUL in a
    goal kills the master at dispatch.
    """
    out: dict = {}
    for line in raw.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = "".join(c if c.isprintable() else " " for c in value).strip()
        if not value:
            continue
        if key in _TEXT:
            out[key] = _clip(value, _TEXT[key])
        elif key in _FLAGS:
            word = value.lower()
            if word in ("yes", "no"):
                out[key] = word == "yes"
    return out


def _clip(value: str, limit: int) -> str:
    """At most ``limit`` characters, cut at a word when one is close, ellipsised.

    A backstop: the goal asks for a sentence within the cap. Cut at the last
    space at or before ``limit - 1`` when that keeps at least half the cap,
    otherwise mid-token at ``limit - 1``; the ellipsis makes it ``limit`` at most.
    """
    if len(value) <= limit:
        return value
    cut = value.rfind(" ", 0, limit)
    if cut >= limit // 2:
        return value[:cut].rstrip() + "…"
    return value[: limit - 1] + "…"


def lengths(answer: str | None) -> dict:
    """Raw, unclipped action and stance lengths from the last block; only keys present."""
    blocks = _BLOCK_RE.findall(answer) if isinstance(answer, str) and answer else []
    out: dict = {}
    for line in (blocks[-1].splitlines() if blocks else []):
        key, sep, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if sep and value and key in (ACTION, STANCE):
            out[f"{key}_chars"] = len(value)
    return out


def strip(answer: str | None) -> str:
    """The answer with its turn blocks removed.

    The signals are consumed by ``reduce``; leaving them in the transcript
    shows the reader plumbing. Ordinary code fences are untouched -- the tag is
    what identifies this one.
    """
    if not isinstance(answer, str) or not answer:
        return ""
    return _BLOCK_RE.sub("", answer).strip()


def pair(value: str) -> tuple[str, str, str] | str:
    """``<role> <role>: <topic>`` as ``(a, b, topic)``, or why it is not one.

    The line an ``align`` or a ``meet_N`` value carries. Only the first colon
    splits, so a topic keeps its own colons. The roles may be split by commas
    or spaces and are lowercased, as role keys are. A reason is the drop reason
    reduce records: ``"malformed"`` (no colon, or not exactly two roles;
    checked first) or ``"no topic"``. Whether the roles are seated is reduce's
    question, not this parser's.
    """
    roles, sep, topic = value.partition(":")
    names = [name.lower() for name in re.split(r"[,\s]+", roles) if name]
    if not sep or len(names) != 2:
        return "malformed"
    topic = topic.strip()
    if not topic:
        return "no topic"
    return names[0], names[1], topic


# Asked for in prose rather than in the worked example, exactly as `action`
# is. The example exists to be copied verbatim, and a copied
# `stance: <20 words or fewer>` would mint that placeholder as the persona's
# stance -- and a stance, unlike a flag, is rendered back as what the speaker said.
_STANCE_SENTENCE = "Add a `stance: <20 words or fewer>` line saying where you now stand and why. "


# The pause offer, appended to a meeting instruction only when seed asks for
# it. One sentence: it rides in the owner's goal, the tightest in the budget.
_ALIGN_SENTENCE = (
    " If two members must align first, add `align: <role> <role>: <topic>`;"
    " the role keys are under `## committee seated`."
)


def instruction(owner: bool = False, *, align: bool = False) -> str:
    """What to tell a speaker so that ``parse`` can read it back.

    Terse on purpose: this rides in every goal, and a goal has a hard character
    budget it shares with the persona, the charge and two paths. A wordier
    instruction buys nothing and costs the speaker the context it needs.

    The worked example sets every flag to ``no``. A speaker that copies the
    template verbatim then says nothing, which is the harmless outcome; a
    template showing ``delegate: yes`` would make the careless copy mint a
    junk edit.

    Only the owner is shown ``delegate``, ``action`` and ``close``: reduce
    drops those from anyone else, so documenting them to a reviewer only
    invites a block that is thrown away. ``stance`` is shown to both -- no gate
    drops it, and a reviewer's is exactly the one a reader wants.

    ``align`` appends one sentence offering ``align: <role> <role>: <topic>``,
    the pause for a 1:1. That offer is the one role decision made above this:
    seed passes ``align`` only for the owner and the manager, and only while
    the run's 1:1 budget can hold a 1:1; ``_apply_block`` still drops an
    ``align`` from anyone else. No other role filtering is needed here:
    ``goal`` returns early for the chair and the junior IC, and the plan and
    the 1:1s get their own shapes (``plan_instruction``,
    ``one_on_one_instruction``), so the owner and the seated reviewers are the
    only speakers handed this, exactly the speakers offered a stance.
    """
    return _meeting_instruction(owner) + (_ALIGN_SENTENCE if align else "")


def _meeting_instruction(owner: bool) -> str:
    """The meeting block and its prose, without the align offer."""
    if owner:
        return (
            "\n\nEnd with this block, nothing after it:\n\n"
            f"```{FENCE_TAG}\n"
            "request_floor: no\n"
            "delegate: no\n"
            "close: no\n"
            "```\n\n"
            "Set delegate: yes only with an `action: <one sentence, 200 "
            "characters or fewer>` line naming the change the junior IC must "
            "make; without one the delegation is dropped. close: yes ends the "
            "discussion and sends the artifact "
            f"to the chair. {_STANCE_SENTENCE}Omit a line you do not mean: an "
            "omitted line is read as unstated, never as yes."
        )
    return (
        "\n\nEnd with this block, nothing after it:\n\n"
        f"```{FENCE_TAG}\n"
        "request_floor: no\n"
        "```\n\n"
        "Set request_floor: yes only if you need a second turn after hearing "
        f"the others; the chair grants the floor in request order. {_STANCE_SENTENCE}"
        # "the line" dangled: it sat immediately after an imperative to ADD a
        # stance line, so a model could read it as permission to omit the stance
        # it had just been told to write -- and "never as yes" is meaningless
        # for free text. Name the line it is about, the way the owner branch's
        # "Omit a line you do not mean" does.
        "Omit the request_floor line if you do not mean it: an omitted line is "
        "read as unstated, never as yes."
    )


def plan_instruction() -> str:
    """What to tell the owner in the plan, so ``parse`` and ``pair`` read it back.

    The worked example is one placeholder line, never a real pair: a copied
    ``meet_1: <host> <guest>: <topic>`` names no seated role, so reduce drops
    it as ``unknown role`` and a verbatim copy schedules nothing, the harmless
    outcome a copied ``no`` gives in the meeting block. ``meet_4`` and above
    are not keys, so the parser drops a fourth line.
    """
    return (
        "\n\nEnd with this block, nothing after it:\n\n"
        f"```{FENCE_TAG}\n"
        "meet_1: <host> <guest>: <topic>\n"
        "```\n\n"
        "Write one line per 1:1 you want, `meet_1`, `meet_2` and `meet_3` at "
        "most, replacing the placeholders. The host is `owner` or `manager`; "
        "the guest is another seated role key, never `owner` or `junior_ic`. "
        "Omit every meet line to hold none."
    )


# A 1:1 host's outcome, asked for in prose for the reason `_STANCE_SENTENCE`
# gives: a copied `agreed: <one line>` would be recorded as the outcome the
# room reads.
_OUTCOME_SENTENCE = (
    "Add `agreed: <one line>` and `still_open: <one line>` lines; the room "
    "reads only those two. "
)


def one_on_one_instruction(*, host: bool, owner: bool, closing: bool) -> str:
    """What to tell one 1:1 speaker, by shape, so ``parse`` can read it back.

    - A member exchange (``closing=False``) states ``aligned``. The template
      shows ``aligned: no``, so a verbatim copy never ends the 1:1.
    - The host (``host=True``, and whoever takes the closing exchange) is asked
      in prose for ``agreed`` and ``still_open`` on every exchange it takes.
    - The owner is asked in prose for ``delegate`` and ``action``, never shown
      ``delegate: no``: the latest block that states ``delegate`` is the edit
      the junior IC makes before the meeting resumes, so a template copied on
      a later exchange would withdraw the edit she already asked for.
    - A closing exchange has no ``aligned`` to state, so it has no template;
      its prose names the fence and the keys.

    The meeting keys (``request_floor``, ``close``, ``align``, ``meet_N``) are
    never shown, because nothing inside a 1:1 honours them. Nor is ``stance``,
    which a 1:1 does not record.
    """
    flags = [] if closing else ["aligned: no"]
    prose = ""
    if not closing:
        prose += (
            "Set aligned: yes only once you and the other member agree on the "
            "topic. "
        )
    if host or closing:
        prose += _OUTCOME_SENTENCE
    if owner:
        prose += (
            f"Set delegate: yes only with an `{ACTION}: <one sentence, "
            f"{ACTION_MAX} characters or fewer>` line naming the edit the "
            "junior IC makes before the meeting resumes. "
        )
    if not flags:
        return f"\n\n{prose}End with them in one `{FENCE_TAG}` fenced block, nothing after it."
    body = "\n".join(flags)
    return (
        "\n\nEnd with this block, nothing after it:\n\n"
        f"```{FENCE_TAG}\n{body}\n```\n\n"
        f"{prose}Omit a line you do not mean: an omitted line is read as "
        "unstated, never as yes."
    )
