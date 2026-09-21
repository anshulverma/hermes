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
line-oriented ``key: value``. Three of the four values are yes/no and the
fourth is one line of English; asking an agent for JSON here buys nothing and
costs a whole class of quoting failures.

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
KEYS: tuple[str, ...] = ("request_floor", "delegate", ACTION, "close")

# An action rides in a goal that shares a hard character budget with the
# persona and both paths, and it names one edit. One line is the whole point.
ACTION_MAX = 200

# The keys whose value is yes/no; `action` is the free-text one. DERIVED from
# KEYS, not a second list: a fifth signal added to KEYS alone would be declared
# vocabulary that `_one` silently drops, with a green suite either way.
_FLAGS = tuple(key for key in KEYS if key != ACTION)

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
    """
    out: dict = {}
    for line in raw.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key == ACTION:
            out[ACTION] = value[:ACTION_MAX]
        elif key in _FLAGS:
            word = value.lower()
            if word in ("yes", "no"):
                out[key] = word == "yes"
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


def instruction(owner: bool = False) -> str:
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
    invites a block that is thrown away.
    """
    if owner:
        return (
            "\n\nEnd with this block, nothing after it:\n\n"
            f"```{FENCE_TAG}\n"
            "request_floor: no\n"
            "delegate: no\n"
            "close: no\n"
            "```\n\n"
            "Set delegate: yes only with an `action: <one line>` line naming "
            "the change the junior IC must make -- without one the delegation "
            "is dropped. close: yes ends the discussion and sends the artifact "
            "to the chair. Omit a line you do not mean: an omitted line is read "
            "as unstated, never as yes."
        )
    return (
        "\n\nEnd with this block, nothing after it:\n\n"
        f"```{FENCE_TAG}\n"
        "request_floor: no\n"
        "```\n\n"
        "Set request_floor: yes only if you need a second turn after hearing "
        "the others; the chair grants the floor in request order. Omit the line "
        "if you do not mean it: an omitted line is read as unstated, never as yes."
    )
