"""Who sits on the committee: the seat lists the three selectors hand the master.

Before the opening round the owner proposes a committee, her manager amends it
and the chair ratifies it. Each of them answers in prose and ends with one
fenced block tagged ``hermes-selection`` holding a JSON object, the convention
``playbooks/research/verdict.py`` established: present and parseable, or
absent. The block is never added to ``turnblock.KEYS``; it is its own channel.

A block is a fence as Markdown renders it, found by voice's own fence reader:
the opener and the closer each stand on their own line. So a block quoted in
prose, indented as code or echoed inside another fence is text, and never
replaces the list above it; and every block parse reads is one voice's measure
leaves out of the word count.

Everything in the block is worker text, so nothing in it is trusted. ``parse``
keeps only the keys this module defines, ``validate`` checks every seat against
the slug rule, the reserved roles and the seat library, and every string a
worker wrote is cleaned, dash-mapped and clipped before it can reach a goal, the
thread or the view. A library slug takes its hand-written persona whatever the
worker said about it; a derived seat gets clipped fields and
``cast.DERIVED_STYLE``.

Pure and stdlib-only. It imports cast and voice, and neither imports it.
"""
from __future__ import annotations

import json
import re

from playbooks.committee import cast, voice

# The info string on the fence. Deliberately not `json`: a selector may quote
# ordinary JSON, and only this tag means "this is my seat list".
FENCE_TAG = "hermes-selection"

# Reviewer seats per committee. senior_director and manager are two of them and
# always seated, so a usable list names at least one more and at most ten more.
MIN_REVIEWERS = 3
MAX_REVIEWERS = 12

# A seat's slug becomes a phase name (tNN-<slug>) and an image name, so it is
# short, lowercase and path-safe. fullmatch, never match: `$` also matches
# before a trailing newline.
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,23}$")

# Roles a selector cannot seat: the fixed four are always seated, and "chair"
# and "unattributed" are names the view and the cast already mean something by.
RESERVED = frozenset(
    {"owner", "manager", "senior_director", "junior_ic", "chair", "unattributed"}
)

# Clip limits for worker text. A derived persona rides in every goal that seat
# receives, and a goal has a hard GOAL_MAX budget.
NAME_MAX = 60
TITLE_MAX = 80
FIELD_MAX = 120
RATIONALE_MAX = 200
STAKEHOLDER_MAX = 80
REASON_MAX = 200

# The only keys that survive parse. Anything else a worker writes (nominated_by,
# style, source, ...) is dropped: those are the master's to decide.
_SEAT_KEYS = (
    "role", "rationale", "name", "title", "altitude", "goal", "ambition", "stake", "lens",
)
_NOT_SEATED_KEYS = ("stakeholder", "reason", "represented_by")

# The brief fields a derived seat carries at FIELD_MAX.
_FIELDS = ("altitude", "goal", "ambition", "stake", "lens")

# Voice's rule 5: no en or em dash in anything a worker reads back.
_DASHES = str.maketrans({"\u2013": "-", "\u2014": "-"})


def _blocks(lines: list[str]) -> list[tuple[int, int]]:
    """(opener, closer) line indexes of every closed hermes-selection fence.

    voice's reader, so the grammar is exactly the one its measure uses: an
    opener is a line of three or more backticks or tildes, indented at most
    three spaces, whose info string is the tag (any case); it closes on the
    next line of the same character, at least as long, and nothing else. An
    unclosed fence is prose. One pass over the lines: linear on any input.
    """
    return [(s, e) for s, e, info in voice._fences(lines) if info == FENCE_TAG]


def parse(answer: str | None) -> tuple[dict | None, str | None]:
    """The seat list an answer carries, as ``(doc, None)``, or ``(None, code)``.

    The last block that parses to a JSON object wins: a selector who restates
    her list has settled on the later one, and a broken restatement does not
    erase the list before it. ``code`` is ``"no_block"`` when there is no
    block and ``"unparseable"`` when no block parses to an object. Never raises.
    """
    if not isinstance(answer, str) or not answer:
        return None, "no_block"
    lines = answer.splitlines()
    blocks = _blocks(lines)
    if not blocks:
        return None, "no_block"
    for start, end in reversed(blocks):
        try:
            doc = json.loads("\n".join(lines[start + 1:end]))
        except (ValueError, RecursionError):  # nesting past the limit is a RecursionError
            continue
        if isinstance(doc, dict):
            return {
                "seats": [_keep(e, _SEAT_KEYS) for e in _entries(doc, "seats")],
                "not_seated": [
                    _keep(e, _NOT_SEATED_KEYS) for e in _entries(doc, "not_seated")
                ],
            }, None
    return None, "unparseable"


def strip(answer: str | None) -> str:
    """The answer with every hermes-selection block removed, whole lines.

    The master renders the list itself, so leaving the raw JSON in the thread
    only shows the reader plumbing. It removes exactly the blocks ``parse``
    reads; every other line, other fences included, is kept as written.
    """
    if not isinstance(answer, str) or not answer:
        return ""
    cut = {k for s, e in _blocks(answer.splitlines()) for k in range(s, e + 1)}
    kept = answer.splitlines(keepends=True)  # the same lines, endings kept
    return "".join(line for k, line in enumerate(kept) if k not in cut).strip()


def not_seated(doc: dict | None) -> list[dict]:
    """The stakeholders a selector named but did not seat, cleaned.

    An entry without both a stakeholder and a reason (non-blank strings) is
    dropped. ``represented_by`` is kept as the worker wrote it (stripped);
    whether it names a seated member is ``resolve``'s question.
    """
    out = []
    for entry in _entries(doc, "not_seated"):
        stakeholder = _clip(entry.get("stakeholder"), STAKEHOLDER_MAX)
        reason = _clip(entry.get("reason"), REASON_MAX)
        if not (stakeholder and reason):
            continue
        rep = entry.get("represented_by")
        out.append({
            "stakeholder": stakeholder,
            "reason": reason,
            "represented_by": rep.strip() if isinstance(rep, str) else None,
        })
    return out


def validate(doc: dict | None, library: dict) -> tuple[list[dict], list[dict]]:
    """``(seats, invalid)`` from a seat list, by the C4 entry rules in order.

    A bad slug is invalid. A reserved role is ignored, because the fixed seats
    are always seated. A repeated slug is ignored: the first entry carrying it
    decides it, even an invalid one. A library slug takes ``{**library[slug]}``
    and the worker's fields are ignored. Any other slug is derived and needs a
    title, and every seat needs a rationale. Each seat is a new dict;
    ``nominated_by`` is added later by ``resolve``. Never raises.
    """
    seats: list[dict] = []
    invalid: list[dict] = []
    seen: set[str] = set()
    # ponytail: no cap on entries, so the output grows linearly with the block;
    # cap the list here if a live selector ever sends thousands.
    for entry in _entries(doc, "seats"):
        role = entry.get("role")
        if not isinstance(role, str) or not SLUG_RE.fullmatch(role):
            invalid.append(_invalid(role, None, "bad slug"))
            continue
        if role in RESERVED or role in seen:
            continue
        seen.add(role)
        if role in library:
            persona, source = library[role], "library"
        elif title := _clip(entry.get("title"), TITLE_MAX):
            persona = {
                "name": _clip(entry.get("name"), NAME_MAX)
                or _clip(entry["title"], NAME_MAX),
                "title": title,
                **{k: _clip(entry.get(k), FIELD_MAX) for k in _FIELDS},
                "style": cast.DERIVED_STYLE,
            }
            source = "derived"
        else:
            invalid.append(_invalid(role, role, "no title"))
            continue
        rationale = _clip(entry.get("rationale"), RATIONALE_MAX)
        if not rationale:
            invalid.append(_invalid(role, role, "no rationale"))
            continue
        seats.append({"role": role, **persona, "rationale": rationale, "source": source})
    return seats, invalid


def _entries(doc: object, key: str) -> list[dict]:
    """The dict entries of ``doc[key]``; ``[]`` when it is not a list."""
    value = doc.get(key) if isinstance(doc, dict) else None
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def _keep(entry: dict, keys: tuple[str, ...]) -> dict:
    return {k: entry[k] for k in keys if k in entry}


def _clip(value: object, limit: int) -> str:
    """Worker text as one clean line of at most ``limit`` characters.

    A non-string is "" (unsaid, never its repr). Every character that is not
    printable (a control, NUL, a lone surrogate, a bidi override) becomes a
    space, so the text is safe in a goal's argv, a UTF-8 file and the view;
    en/em dashes become "-"; then ``cast.clip`` collapses whitespace and cuts.
    "" means blank.
    """
    if not isinstance(value, str):
        return ""
    clean = "".join(c if c.isprintable() else " " for c in value)
    return cast.clip(clean.translate(_DASHES), limit)


def _invalid(raw: object, role: str | None, why: str) -> dict:
    return {
        "stakeholder": _clip(raw, STAKEHOLDER_MAX) or "(unnamed)",
        "role": role,
        "reason": f"invalid: {why}",
        "represented_by": None,
    }
