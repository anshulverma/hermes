"""Who sits on the committee: the seat lists the three selectors hand the master.

Before the opening round the owner proposes a committee, her manager amends it
and the chair ratifies it. Each of them answers in prose and ends with one
fenced block tagged ``hermes-selection`` holding a JSON object, the convention
``playbooks/research/verdict.py`` established: present and parseable, or
absent. The block is never added to ``turnblock.KEYS``; it is its own channel.

A block is found by voice's own fence reader: the opener and the closer each
stand on their own line, indented at most three spaces. So a block quoted in
prose, opened mid-line, indented four spaces or echoed inside another fence is
text and cannot replace the list above it, and every block parse reads is one
voice's measure leaves out of the word count. The reader is line-based, not a
Markdown renderer: a tab-indented fence under a list item, a thematic break or
setext underline read as a list opener, or an HTML comment or div wrapper can
still let text Markdown shows as code count as a block (voice's to fix).

Everything in the block is worker text, so nothing in it is trusted. ``parse``
keeps only the keys this module defines, ``validate`` checks every seat against
the slug rule, the reserved roles and the seat library, and every string a
worker wrote is cleaned, dash-mapped and clipped before it can reach a goal, the
thread or the view. A library slug takes its hand-written persona whatever the
worker said about it; a derived seat gets clipped fields and
``cast.DERIVED_STYLE``.

``resolve`` turns the three kept lists into the run's committee. The chair's
list is final and the fixed four are always seated. Everyone else a selector
named is recorded as considered, with a reason and, when one is seated, a
representative. A chair list that cannot seat anyone falls back to today's
seven reviewers (``fallback``), and nothing here raises on a parsed list. The
record stays bounded however long the block: each stage's first INVALID_MAX
invalid entries and the first CONSIDERED_MAX considered are kept, and the
result counts the rest as ``invalid_dropped`` and ``considered_dropped``, so
nothing vanishes silently.

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
FIELD_MAX = 94
RATIONALE_MAX = 200
STAKEHOLDER_MAX = 80
REASON_MAX = 200

# How much of a long list reaches the reduction and thread.md: a 200 KB block
# must not write thousands of entries. What is cut is counted, never silent.
INVALID_MAX = 20  # per stage
CONSIDERED_MAX = 40

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

# Printable characters that render as nothing: the Hangul fillers, the blank
# Braille cell and the combining grapheme joiner. The zero-width ones are
# already unprintable.
_INVISIBLE = frozenset("\u115f\u1160\u3164\uffa0\u2800\u034f")

def _name_key(name: str) -> str:
    """A name reduced to its casefolded letters and digits: "Maya Okonkwo." and
    "maya-okonkwo" are the same person to a reader, "Maya Okonkwo-Reyes" is not."""
    return "".join(ch for ch in name.casefold() if ch.isalnum())


def _keys(text: str) -> set[str]:
    """``_name_key(text)`` and its words in any order, for matching a stakeholder
    to a seat: "Staff Engineer" is staff_ic's title, and "Partner team
    engineering lead" is partner_owner's "Engineering Lead, partner team"."""
    words = "".join(ch if ch.isalnum() else " " for ch in text.casefold()).split()
    return {_name_key(text), " ".join(sorted(words))} - {""}


def _seat_keys(seat: dict) -> set[str]:
    """Every key a stakeholder note may name ``seat`` by: its slug, title or name."""
    return set().union(*(_keys(str(seat.get(k) or "")) for k in ("role", "title", "name")))


# Every cast and library persona's name as a `_name_key`: a derived seat by one of
# these would read in the thread and view as that person.
_TAKEN = frozenset(
    _name_key(cast.clip(p["name"], NAME_MAX))
    for p in (*cast.CAST.values(), *cast.LIBRARY.values())
)


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
            # strict=False: splitlines also breaks on U+2028, U+2029 and U+0085,
            # so a raw one inside a JSON string comes back as a raw newline
            doc = json.loads("\n".join(lines[start + 1:end]), strict=False)
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
    whether it names a seated member is ``resolve``'s question. It is
    lowercased, and "owner" is no representative: the proposal's owner is not
    the voice of someone reviewing her proposal.
    """
    out = []
    for entry in _entries(doc, "not_seated"):
        stakeholder = _clip(entry.get("stakeholder"), STAKEHOLDER_MAX)
        reason = _clip(entry.get("reason"), REASON_MAX)
        if not (stakeholder and reason):
            continue
        rep = entry.get("represented_by")
        rep = rep.strip().lower() if isinstance(rep, str) else ""
        out.append({
            "stakeholder": stakeholder,
            "reason": reason,
            "represented_by": rep if rep and rep != cast.OWNER else None,
        })
    return out


def validate(doc: dict | None, library: dict) -> tuple[list[dict], list[dict]]:
    """``(seats, invalid)`` from a seat list, by the C4 entry rules in order.

    A bad slug is invalid. A reserved role is ignored, because the fixed seats
    are always seated. A repeated slug is ignored: the first entry carrying it
    decides it, even an invalid one. A library slug takes ``{**library[slug]}``
    and the worker's fields are ignored. Any other slug is derived and needs a
    title and a name no cast or library persona has (any case); a name with no
    letter or digit is blank, a nameless seat is named from its title, and a
    blank stake is the rationale. Every seat needs a rationale.
    Each seat is a new dict;
    ``nominated_by`` is added later by ``resolve``. Never raises.
    """
    seats: list[dict] = []
    invalid: list[dict] = []
    seen: set[str] = set()
    # No cap here, so the output grows linearly with the block; resolve records
    # at most INVALID_MAX invalid entries per stage and counts the rest.
    for entry in _entries(doc, "seats"):
        role = entry.get("role")
        if not isinstance(role, str) or not SLUG_RE.fullmatch(role):
            invalid.append(_invalid(role, None, "bad slug"))
            continue
        if role in RESERVED or role in seen:
            continue
        seen.add(role)
        rationale = _clip(entry.get("rationale"), RATIONALE_MAX)
        if role in library:
            persona, source = library[role], "library"
        elif title := _clip(entry.get("title"), TITLE_MAX):
            name = _clip(entry.get("name"), NAME_MAX)
            # combining marks alone render as nothing: blank, so named from the title
            name = name if _name_key(name) else cast.clip(title, NAME_MAX)
            if _name_key(name) in _TAKEN:
                invalid.append(_invalid(role, role, "name taken"))
                continue
            fields = {k: _clip(entry.get(k), FIELD_MAX) for k in _FIELDS}
            # never an empty persona: an unsaid stake is why the seat was put forward
            fields["stake"] = fields["stake"] or cast.clip(rationale, FIELD_MAX)
            persona = {"name": name, "title": title, **fields, "style": cast.DERIVED_STYLE}
            source = "derived"
        else:
            invalid.append(_invalid(role, role, "no title"))
            continue
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
    printable (a control, NUL, a lone surrogate, a bidi override), renders as
    nothing (``_INVISIBLE``) or lies above U+FFFF (two UTF-16 units each, and
    a goal's budget holds in those too) becomes a space, so the text is safe
    in a goal's argv, a UTF-8 file and the view, and invisible text is blank;
    en/em dashes become "-"; then ``cast.clip`` collapses whitespace and cuts.
    "" means blank.
    """
    if not isinstance(value, str):
        return ""
    clean = "".join(
        c if c.isprintable() and c not in _INVISIBLE and c <= "\uffff" else " " for c in value
    )
    return cast.clip(clean.translate(_DASHES), limit)


def _invalid(raw: object, role: str | None, why: str) -> dict:
    return {
        "stakeholder": _clip(raw, STAKEHOLDER_MAX) or "(unnamed)",
        "role": role,
        "reason": f"invalid: {why}",
        "represented_by": None,
    }


# --- resolution ----------------------------------------------------------

# The seats no selection can empty (Q5), in roster order.
_FIXED = ("owner", "senior_director", "manager", "junior_ic")

# A stage or fallback code as the thread, a retake note and a seat's reason say it.
_WORDS = {
    "chair_failed": "the chair gave no usable list",
    "no_answer": "no answer was delivered",
    "no_block": "no hermes-selection block",
    "unparseable": "a hermes-selection block that did not parse",
    "too_few": "no valid seats",
    "lost": "the selection was lost with the process that held it",
}


def fallback_words(code: object) -> str:
    """``code`` in words (D8); a code this module does not know is itself, cleaned."""
    said = _WORDS.get(code) if isinstance(code, str) else None
    return said or _clip(code, STAKEHOLDER_MAX) or "no reason given"


def fixed_seats() -> dict[str, dict]:
    """The four fixed seats as new seat records, in roster order.

    ``open``, ``resolve``, ``fallback`` and the tests all take the fixed four
    from here, so a fixed seat reads the same on every path.
    """
    return {
        role: {
            **cast.CAST[role],
            "role": role,
            "rationale": cast.FIXED_RATIONALE[role],
            "nominated_by": "fixed",
            "source": "fixed",
        }
        for role in _FIXED
    }


def stage_code(delivered: bool, parse_code: str | None, seats: list) -> str | None:
    """Why one stage's list cannot seat a committee, or None when it can.

    ``too_few`` counts the two fixed reviewers, so it means no valid seat at
    all (D2 rule 3).
    """
    if not delivered:
        return "no_answer"
    if parse_code:
        return parse_code
    if 2 + len(seats) < MIN_REVIEWERS:
        return "too_few"
    return None


def resolve(stages: list[dict], library: dict) -> dict:
    """The run's committee from the selectors' kept lists (D2 rules 1-7).

    ``stages`` is the playbook's ``s["stages"]``: ``{stage, role, delivered,
    doc, code}`` per kept take, in stage order. The chair's stage-3 list is
    final. Stages 1-2 only decide who put a seat forward and who was
    considered, so their failure never costs the run its committee. A chair
    list that cannot seat anyone gives ``fallback(code)``, with an undelivered
    chair reported as ``chair_failed``.

    Returns ``{seated, reviewers, considered, considered_dropped,
    invalid_dropped, fallback}``: ``seated`` is the owner, the reviewers in
    opening order, then the junior IC; the two counts are what the caps cut
    (``_considered``). Deterministic, and linear in the lists' length:
    ``validate`` keeps no cap on entries, so the reviewers are cut to
    MAX_REVIEWERS here and the rest are considered.
    """
    chair = next((st for st in reversed(stages) if st.get("stage") == 3), None)
    delivered = bool(chair and chair.get("delivered"))
    stored = chair.get("code") if chair else None
    # recomputed, never trusted (a stored None over a list with no valid seat
    # would seat two reviewers); the list is read only when its size decides
    seats = validate(chair.get("doc"), library)[0] if delivered and not stored else []
    code = stage_code(delivered, stored, seats)
    if code is not None:
        out = fallback("chair_failed" if code == "no_answer" else code)
        try:
            earlier = [_read(st, library) for st in stages if st.get("stage") != 3]
            out.update(_considered(earlier, out, []))
        except Exception:
            out["considered"] = []  # the default committee never waits on its footnotes
        return out
    read = [_read(st, library) for st in stages]
    ratified = next(r for r in reversed(read) if r["stage"] == 3)
    room = MAX_REVIEWERS - 2  # senior_director and manager hold two reviewer seats
    chosen = [
        {**seat, "nominated_by": next(r["role"] for r in read if seat["role"] in r["slugs"])}
        for seat in ratified["seats"][:room]
    ]
    fixed = fixed_seats()
    out = {
        "seated": [
            fixed["owner"], fixed["senior_director"], fixed["manager"],
            *chosen, fixed["junior_ic"],
        ],
        "reviewers": ["senior_director", "manager", *(seat["role"] for seat in chosen)],
        "considered": [],
        "considered_dropped": 0,
        "invalid_dropped": 0,
        "fallback": None,
    }
    out.update(_considered(read, out, ratified["seats"][room:]))
    return out


def fallback(code: str) -> dict:
    """Today's committee, for a chair list that cannot seat anyone (D2 rule 7).

    The fixed four plus the default reviewers from ``cast.CAST``, in roster
    order, with ``reviewers`` equal to ``cast.SENIORITY``. It reads no stage
    data, so it cannot fail the way the list did.
    """
    fixed = fixed_seats()
    why = f"in the default committee ({fallback_words(code)})"
    reviewers = [
        fixed.get(role) or {
            **cast.CAST[role],
            "role": role,
            "rationale": why,
            "nominated_by": "default",
            "source": "library",
        }
        for role in cast.SENIORITY
    ]
    return {
        "seated": [fixed["owner"], *reviewers, fixed["junior_ic"]],
        "reviewers": list(cast.SENIORITY),
        "considered": [],
        "considered_dropped": 0,
        "invalid_dropped": 0,
        "fallback": code,
    }


def _read(stage: dict, library: dict) -> dict:
    """One kept stage, validated: its seats, first INVALID_MAX invalid entries and notes."""
    doc = stage.get("doc")
    seats, invalid = validate(doc, library)
    return {
        "stage": stage.get("stage"),
        "role": stage.get("role"),
        "code": stage.get("code"),
        "seats": seats,
        "slugs": {seat["role"] for seat in seats},
        "invalid": invalid[:INVALID_MAX],
        "invalid_dropped": max(0, len(invalid) - INVALID_MAX),
        "notes": not_seated(doc),
    }


def _considered(read: list[dict], resolved: dict, overflow: list[dict]) -> dict:
    """Everyone named and not seated, one entry per key (D2 rules 4 and 6).

    A seat's key is its slug (a bad slug's, its raw role lowercased) and a
    note's is its stakeholder lowercased, or the slug of the listed seat it
    names by slug, title or persona name, words in any order (``_keys``), so
    a seat and a note about it are one entry. Stages are read in order, so the
    latest stage wins a key. A note naming a seated seat is dropped: that
    stakeholder is seated. A stage 1-2 seat that did not make the roster is
    dropped by the first later usable list that leaves it out, whose note on
    it gives the reason. No entry whose key is a seated slug survives, and a
    representative must be seated (never the owner), except that an overflow
    seat always names one.

    Returns ``{considered, considered_dropped, invalid_dropped}``: the first
    CONSIDERED_MAX entries in that order, how many more there were, and how
    many invalid entries ``_read`` cut, summed over the stages read.
    """
    seated = {seat["role"] for seat in resolved["seated"]}
    taken = set().union(*map(_seat_keys, resolved["seated"]))
    # every key of every listed seat that is not seated -> its slug, the first
    # listing winning: one pass, so a note is matched in constant time
    listed: dict[str, dict] = {}
    for st in read:
        for seat in st["seats"]:
            if seat["role"] not in seated:
                listed.setdefault(seat["role"], seat)
    names = {key: slug for slug, seat in reversed(listed.items()) for key in _seat_keys(seat)}
    found: dict[str, dict] = {}
    notes_by_stage = []
    for i, st in enumerate(read):
        for entry in st["invalid"]:
            found[entry["role"] or entry["stakeholder"].lower()] = dict(entry)
        notes = {}  # key -> note: a named seat's slug, else the stakeholder lowercased
        for note in st["notes"]:
            keys = _keys(note["stakeholder"])
            if keys & taken:
                continue
            slug = next((names[key] for key in sorted(keys) if key in names), None)
            key = slug or note["stakeholder"].strip().lower()
            notes[key] = note
            seat = listed.get(slug) if slug else None
            found[key] = _entry(
                seat["title"] if seat else note["stakeholder"], slug, note["reason"],
                _rep(note["represented_by"], seated),
            )
        notes_by_stage.append(notes)
        for k, earlier in enumerate(read[:i]):
            for seat in earlier["seats"]:
                slug = seat["role"]
                if slug in seated or _dropper(read, k, slug) is not st:
                    continue
                note = notes.get(slug)
                found[slug] = _entry(
                    seat["title"], slug,
                    note["reason"] if note else f"dropped by {cast.CAST[st['role']]['name']}",
                    _rep(note["represented_by"], seated) if note else None,
                )
    if resolved["fallback"]:
        for k, st in enumerate(read):
            for seat in st["seats"]:
                slug = seat["role"]
                if slug not in seated and _dropper(read, k, slug) is None:
                    found[slug] = _entry(
                        seat["title"], slug,
                        f"not in the default committee ({fallback_words(resolved['fallback'])})",
                        None,
                    )
    chair_notes = next((n for st, n in zip(read, notes_by_stage) if st["stage"] == 3), {})
    for seat in overflow:
        note = chair_notes.get(seat["role"]) or {}
        found[seat["role"]] = _entry(
            seat["title"], seat["role"], f"over the {MAX_REVIEWERS}-seat bound",
            _rep(note.get("represented_by"), seated) or "senior_director",
        )
    kept = [entry for key, entry in found.items() if key not in seated]
    return {
        "considered": kept[:CONSIDERED_MAX],
        "considered_dropped": max(0, len(kept) - CONSIDERED_MAX),
        "invalid_dropped": sum(st["invalid_dropped"] for st in read),
    }


def _dropper(read: list[dict], k: int, slug: str) -> dict | None:
    """The first stage after ``read[k]`` with a usable list that leaves ``slug`` out."""
    return next(
        (st for st in read[k + 1:] if st["code"] is None and slug not in st["slugs"]),
        None,
    )


def _rep(slug: str | None, seated: set[str]) -> str | None:
    """``slug`` when it is a seated seat other than the owner (D1), else None."""
    return slug if slug in seated and slug != cast.OWNER else None


def _entry(stakeholder: str, role: str | None, reason: str, rep: str | None) -> dict:
    return {"stakeholder": stakeholder, "role": role, "reason": reason, "represented_by": rep}
