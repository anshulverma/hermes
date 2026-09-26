"""Tests for the committee's seat selection (playbooks/committee/selection.py).

TDD: written FIRST, watched fail, then the module implemented.

Before the opening round three selectors (the owner, her manager and the chair)
each hand the master a seat list. Like a turn's signals it rides inside the
worker's prose, in a fence with its own tag, so it is present and parseable or
absent. Everything in it is worker text, so every entry is checked, clipped and
cleaned master-side before it can seat anyone.
"""
from __future__ import annotations

import json
import time

from playbooks.committee import cast
from playbooks.committee import selection as S

LONG_DASHES = ("\u2013", "\u2014")

SEAT_KEYS = {
    "role", "name", "title", "altitude", "goal", "ambition", "stake", "lens",
    "style", "rationale", "source",
}


def _block(doc) -> str:
    """One hermes-selection fence around ``doc`` (a dict is JSON-encoded)."""
    body = doc if isinstance(doc, str) else json.dumps(doc)
    return f"```{S.FENCE_TAG}\n{body}\n```"


def _answer(*docs) -> str:
    """A selector's answer: a sentence of prose, then one fence per doc."""
    blocks = "\n\n".join(_block(d) for d in docs)
    return f"I would seat the people who carry the risk.\n\n{blocks}\n"


def _seat(role, **fields) -> dict:
    return {"role": role, "rationale": f"{role} carries a risk in this proposal", **fields}


def _bad(stakeholder: str) -> dict:
    return {
        "stakeholder": stakeholder,
        "role": None,
        "reason": "invalid: bad slug",
        "represented_by": None,
    }


# --- parse ---------------------------------------------------------------

def test_parse_keeps_the_last_fence_that_parses_to_an_object():
    """A selector who restates her list has settled on the later one, and a
    broken restatement does not erase the list before it."""
    legal = {"stakeholder": "Legal", "reason": "no filing", "represented_by": "privacy"}
    first = {"seats": [_seat("security")]}
    second = {"seats": [_seat("sre")], "not_seated": [legal]}
    kept_first = ({"seats": [_seat("security")], "not_seated": []}, None)

    assert S.parse(_answer(first, second)) == (
        {"seats": [_seat("sre")], "not_seated": [legal]},
        None,
    )
    assert S.parse(_answer(first, "{not json", "[1, 2]")) == kept_first
    # an ordinary json fence is not a seat list, whatever it holds
    answer = "```json\n" + json.dumps(second) + "\n```\n\n" + _answer(first)
    assert S.parse(answer) == kept_first
    # Only a fence Markdown renders is a block. A later one quoted, indented as
    # code, opened mid-line or sitting inside another fence is text, so echoing
    # another selector's block cannot replace the list above it.
    later = json.dumps(second)
    for echo in (
        f"> ```{S.FENCE_TAG}\n> {later}\n> ```",
        f"    ```{S.FENCE_TAG}\n    {later}\n    ```",
        f"As she said: ```{S.FENCE_TAG}\n{later}\n```",
        f"````\n```{S.FENCE_TAG}\n{later}\n```\n````",
        f"```json\n```{S.FENCE_TAG}\n{later}\n```\n```",
    ):
        assert S.parse(_answer(first) + "\n" + echo + "\n") == kept_first, echo
    # a ``` inside a JSON string is not a closing fence line
    ticks = {"seats": [_seat("sre", rationale="it pages at 3 a.m. ``` every week")]}
    assert S.parse(_answer(first, ticks))[0]["seats"] == ticks["seats"]
    # a raw U+2028, U+2029 or U+0085 inside a JSON string splits the line for
    # splitlines, not for JSON: the later block still parses and wins
    raw = '{"seats": [{"role": "sre", "rationale": "pages\u2028at\u20293\x85a.m."}]}'
    doc, code = S.parse(_answer(first, raw))
    assert code is None and [s["role"] for s in doc["seats"]] == ["sre"]
    assert S.validate(doc, cast.LIBRARY)[0][0]["rationale"] == "pages at 3 a.m."


def test_parse_reports_no_block_and_unparseable():
    assert S.parse(None) == (None, "no_block")
    assert S.parse("") == (None, "no_block")
    assert S.parse("I would seat security and sre.") == (None, "no_block")
    assert S.parse('```json\n{"seats": []}\n```') == (None, "no_block")
    for body in ("{not json", '["security"]', '"security"', "null", "3", ""):
        assert S.parse(_answer(body)) == (None, "unparseable"), body
    assert S.parse(_answer("{}")) == ({"seats": [], "not_seated": []}, None)
    # Markdown's fence rules: a quoted, code-indented, mid-line, unclosed or
    # nested opener is prose; up to three spaces of indent, the other fence
    # character and the tag in any case are still a fence.
    for prose in (
        f"> ```{S.FENCE_TAG}\n> {{}}\n> ```",
        f"    ```{S.FENCE_TAG}\n    {{}}\n    ```",
        f"See ```{S.FENCE_TAG}\n{{}}\n```",
        f"```{S.FENCE_TAG}\n{{}}",
        f"````\n```{S.FENCE_TAG}\n{{}}\n```\n````",
        f"```{S.FENCE_TAG}x\n{{}}\n```",  # the info string is the tag, whole
        f"```{S.FENCE_TAG} extra\n{{}}\n```",
    ):
        assert S.parse(prose) == (None, "no_block"), prose
    for fence in (
        f"   ```{S.FENCE_TAG}\n{{}}\n```",
        f"~~~{S.FENCE_TAG}\n{{}}\n~~~",
        f"``` {S.FENCE_TAG.upper()} \n{{}}\n```",
    ):
        assert S.parse(fence) == ({"seats": [], "not_seated": []}, None), fence


def test_parse_drops_unknown_keys_and_coerces_malformed_shapes():
    """Only the C4 keys survive: a worker cannot say who put a seat forward,
    style a derived seat, or add a key the master never defined."""
    doc, code = S.parse(_answer({
        "seats": [1, "x", None, ["security"], {
            "role": "crew_owner", "rationale": "runs the crews", "title": "Crew lead",
            "nominated_by": "senior_director", "style": "shouts", "source": "library",
            "extra": 1,
        }],
        "not_seated": [
            {"stakeholder": "Legal", "reason": "no filing", "represented_by": "privacy",
             "vote": "no"},
        ],
        "fallback": "too_few",
        "reviewers": ["security"],
    }))

    assert code is None
    assert doc == {
        "seats": [{"role": "crew_owner", "rationale": "runs the crews", "title": "Crew lead"}],
        "not_seated": [{"stakeholder": "Legal", "reason": "no filing", "represented_by": "privacy"}],
    }
    empty = ({"seats": [], "not_seated": []}, None)
    assert S.parse(_answer({"seats": "security"})) == empty
    assert S.parse(_answer({"seats": {"role": "security"}, "not_seated": {}})) == empty
    # a non-string stakeholder survives parse and is dropped by not_seated
    doc, _ = S.parse(_answer({"not_seated": [{"stakeholder": 7, "reason": "numbers"}]}))
    assert doc["not_seated"] == [{"stakeholder": 7, "reason": "numbers"}]
    assert S.not_seated(doc) == []


def test_parse_never_raises_on_junk():
    """A worker's answer is untrusted text: parse returns a code, never an
    exception, and whatever it returns validate and not_seated accept. On a
    crafted 200 KB answer the whole read stays linear."""
    junk = [
        None, 12, "", "```", f"```{S.FENCE_TAG}", f"```{S.FENCE_TAG}\n",
        f'```{S.FENCE_TAG}\n{{"seats": []}}',  # never closed
        _answer("[" * 100_000),  # nests past the recursion limit
        _answer('{"seats": NaN, "not_seated": Infinity}'),
        _answer('{"seats": [{"role": {"a": 1}, "title": [], "rationale": null}]}'),
        _answer("\x00\ud800"),
    ]
    for answer in junk:
        doc, code = S.parse(answer)
        assert code in (None, "no_block", "unparseable"), answer
        assert doc is None or set(doc) == {"seats", "not_seated"}
        S.validate(doc, cast.LIBRARY)
        S.not_seated(doc)
        S.strip(answer)
    # a number past int's digit limit is unparseable; one past float's is inf
    assert S.parse(_answer('{"seats": ' + "9" * 5000 + "}")) == (None, "unparseable")
    assert S.parse(_answer('{"seats": 1e999, "not_seated": -1e999}')) == (
        {"seats": [], "not_seated": []}, None)

    n = 200_000
    tag = S.FENCE_TAG
    crafted = [
        f"```{tag}\n" * (n // 20),  # openers that never close
        f"```{tag}\n{{\n```\n" * (n // 24),  # thousands of blocks, none parses
        "```\n" * (n // 4), "> ```" * (n // 5), "`" * n, "~" * n, "\r" * n,
        _answer("[" * n), _answer("{" * n), _answer('{"seats": [' + "1" * n + "]}"),
        _answer('{"seats": [' + '{"role": 1},' * (n // 12) + "{}]}"),
        _answer(json.dumps({"seats": [
            {"role": f"r{i}", "title": "t", "rationale": "r"} for i in range(n // 40)
        ]})),
        _answer(json.dumps({
            "seats": [{"role": "crew_owner", "title": "x " * (n // 4),
                       "rationale": "\u2014" * (n // 24)}],  # 6 characters each in JSON
            "not_seated": [{"stakeholder": "y\x00" * (n // 28), "reason": "z"}],
        })),
    ]
    for answer in crafted:
        start = time.perf_counter()
        doc, _ = S.parse(answer)
        S.validate(doc, cast.LIBRARY)
        S.not_seated(doc)
        S.strip(answer)
        assert time.perf_counter() - start < 2.0, answer[:40]


# --- strip ---------------------------------------------------------------

def test_strip_removes_every_selection_fence():
    """The master renders the list itself; the raw JSON is plumbing."""
    turn = "```hermes-turn\nrequest_floor: yes\n```"
    code = '```json\n{"seats": []}\n```'
    answer = (
        "Seat security.\n\n" + _block({"seats": []}) + "\n\n" + code
        + "\n\nAnd sre.\n\n" + _block("{broken") + "\n\n" + turn + "\n"
    )

    out = S.strip(answer)

    assert S.FENCE_TAG not in out and "{broken" not in out
    assert out.startswith("Seat security.") and "And sre." in out
    assert code in out and turn in out  # other fences are untouched
    assert S.strip(None) == "" and S.strip("") == ""
    assert S.strip("No block here.") == "No block here."
    # it removes exactly what parse reads: a quoted block is prose, and stays
    quoted = f"Her list:\n> ```{S.FENCE_TAG}\n> {{}}\n> ```"
    assert S.strip(quoted) == quoted


# --- validate ------------------------------------------------------------

def test_validate_rejects_bad_slugs_and_ignores_reserved_and_duplicate_roles():
    doc = {"seats": [
        _seat("Security"), _seat("sec urity"), _seat("s" * 25), _seat("security\n"),
        _seat("9lives"), _seat("x"), _seat(None), {"rationale": "no role at all"},
        _seat(""),
        *(_seat(r) for r in sorted(S.RESERVED)),
        _seat("security", rationale="first"), _seat("security", rationale="second"),
        _seat("crew_owner"),  # no title: invalid, and it decides the slug
        _seat("crew_owner", title="Crew lead"),
        _seat("s" * 24, title="Longest slug"),
    ]}

    seats, invalid = S.validate(doc, cast.LIBRARY)

    assert [s["role"] for s in seats] == ["security", "s" * 24]
    assert seats[0]["rationale"] == "first"
    assert invalid == [
        _bad("Security"), _bad("sec urity"), _bad("s" * 25), _bad("security"),
        _bad("9lives"), _bad("x"), _bad("(unnamed)"), _bad("(unnamed)"),
        _bad("(unnamed)"),
        {"stakeholder": "crew_owner", "role": "crew_owner",
         "reason": "invalid: no title", "represented_by": None},
    ]
    assert S.RESERVED == {
        "owner", "manager", "senior_director", "junior_ic", "chair", "unattributed",
    }


def test_validate_gives_a_library_role_the_library_persona():
    """A library slug takes the hand-written persona: the worker cannot rename
    or restyle it, only say why it belongs."""
    before = {slug: dict(p) for slug, p in cast.LIBRARY.items()}

    seats, invalid = S.validate({"seats": [
        _seat("security", name="Mallory", title="Chief Everything", lens="ship it",
              rationale="the proposal opens a port \u2014 to everyone"),
        _seat("tpm", name="Nobody", style="loud"),
    ]}, cast.LIBRARY)

    assert invalid == []
    sec, tpm = seats
    assert sec == {
        "role": "security", **cast.LIBRARY["security"],
        "rationale": "the proposal opens a port - to everyone", "source": "library",
    }
    assert tpm == {
        **cast.CAST["tpm"],
        "rationale": "tpm carries a risk in this proposal", "source": "library",
    }
    assert set(sec) == SEAT_KEYS and set(tpm) == SEAT_KEYS
    assert sec is not cast.LIBRARY["security"] and tpm is not cast.CAST["tpm"]
    assert {slug: dict(p) for slug, p in cast.LIBRARY.items()} == before
    # the library is the one passed in: without tpm in it, tpm is derived
    assert S.validate({"seats": [_seat("tpm")]}, {})[1][0]["reason"] == "invalid: no title"


def test_validate_requires_a_title_for_a_derived_seat_and_a_rationale_for_every_seat():
    seats, invalid = S.validate({"seats": [
        {"role": "crew_owner", "rationale": "runs the crews"},
        {"role": "fleet_ops", "title": "   ", "rationale": "x"},
        {"role": "billing", "title": 42, "rationale": "x"},
        {"role": "sre"},
        {"role": "privacy", "rationale": "  "},
        {"role": "legal", "title": "Counsel", "rationale": ["a"]},
        {"role": "support", "title": "Support lead", "rationale": "takes the calls"},
    ]}, cast.LIBRARY)

    assert [s["role"] for s in seats] == ["support"]
    assert [(i["role"], i["reason"]) for i in invalid] == [
        ("crew_owner", "invalid: no title"),
        ("fleet_ops", "invalid: no title"),
        ("billing", "invalid: no title"),
        ("sre", "invalid: no rationale"),
        ("privacy", "invalid: no rationale"),
        ("legal", "invalid: no rationale"),
    ]
    assert all(i["stakeholder"] == i["role"] and i["represented_by"] is None for i in invalid)


def test_validate_rejects_a_derived_seat_named_like_a_cast_or_library_persona():
    """A derived seat cannot speak as someone already in the cast or the library:
    "Maya Okonkwo" under slug "maya" would read in the timeline as the owner."""
    owner, security = cast.CAST["owner"]["name"], cast.LIBRARY["security"]["name"]
    seats, invalid = S.validate({"seats": [
        _seat("maya", name=owner, title="Staff Engineer & proposal owner"),
        _seat("sec_lead", name=f"  {security.upper()} ", title="Security lead"),
        _seat("ruth", title=cast.CAST["manager"]["name"].replace(" ", "\t")),  # name from title
        _seat("maya_two", name="Maya Okonkwo-Reyes", title="Crew lead"),
    ]}, cast.LIBRARY)

    assert [(i["role"], i["reason"]) for i in invalid] == [
        ("maya", "invalid: name taken"),
        ("sec_lead", "invalid: name taken"),
        ("ruth", "invalid: name taken"),
    ]
    assert [(s["role"], s["name"]) for s in seats] == [("maya_two", "Maya Okonkwo-Reyes")]


def test_validate_clips_every_field_and_maps_long_dashes_to_hyphens():
    """Voice's rule 5 holds for derived text too: no en or em dash survives."""
    long = "x" * 500
    seats, invalid = S.validate({"seats": [
        {"role": "crew_owner", "name": long, "title": long, "altitude": long, "goal": long,
         "ambition": long, "stake": long, "lens": long, "rationale": long},
        {"role": "fleet_ops", "title": "Fleet \u2013 operations \u2014 lead",
         "lens": "uptime \u2014 then cost", "rationale": "owns the pager \u2014 and the budget"},
        {"role": "dash_ops", "title": "\u2014" * 500, "rationale": "\u2013" * 500},
    ]}, cast.LIBRARY)

    assert invalid == []
    big, dashed, clipped = seats
    limits = {
        "name": S.NAME_MAX, "title": S.TITLE_MAX, "altitude": S.FIELD_MAX,
        "goal": S.FIELD_MAX, "ambition": S.FIELD_MAX, "stake": S.FIELD_MAX,
        "lens": S.FIELD_MAX, "rationale": S.RATIONALE_MAX,
    }
    for field, limit in limits.items():
        assert big[field] == "x" * (limit - 1) + "\u2026", field
    assert dashed["title"] == dashed["name"] == "Fleet - operations - lead"
    assert dashed["lens"] == "uptime - then cost"
    assert dashed["rationale"] == "owns the pager - and the budget"
    assert clipped["title"] == "-" * (S.TITLE_MAX - 1) + "\u2026"
    assert clipped["name"] == "-" * (S.NAME_MAX - 1) + "\u2026"  # the title, cut to NAME_MAX
    assert clipped["rationale"] == "-" * (S.RATIONALE_MAX - 1) + "\u2026"
    for seat in seats:
        for field, value in seat.items():
            assert not any(d in value for d in LONG_DASHES), field

    # A worker string lands in a goal's argv, a UTF-8 file and the view, so a
    # NUL, a lone surrogate, a control character or a bidi override becomes a
    # space; text that is nothing else is blank.
    dirty = "Crew\x00lead\ud800\u202e\x1b[31m\u200b"
    seats, invalid = S.validate({"seats": [
        {"role": "crew_owner", "title": dirty, "lens": dirty, "rationale": dirty},
        {"role": "fleet_ops", "title": "\x00\u200b\t", "rationale": "x"},
        {"role": "pager", "title": "Pager", "rationale": "\ud800\x7f"},
    ]}, cast.LIBRARY)
    assert [(s["title"], s["lens"], s["rationale"]) for s in seats] == [
        ("Crew lead [31m", "Crew lead [31m", "Crew lead [31m"),
    ]
    assert [i["reason"] for i in invalid] == ["invalid: no title", "invalid: no rationale"]
    assert all(v.isprintable() for v in seats[0].values())
    json.dumps(seats, ensure_ascii=False).encode("utf-8")  # no lone surrogate left
    # printable characters that render as nothing (the Hangul fillers, the
    # blank Braille cell, the combining grapheme joiner) are blank too
    ghosts = "\u3164\u2800\u115f\u1160\uffa0\u034f"
    seats, invalid = S.validate({"seats": [
        {"role": "crew_owner", "title": ghosts, "rationale": "x"},
        {"role": "fleet_ops", "title": "Fleet", "rationale": ghosts},
        {"role": "pager", "title": f"Pager{ghosts}lead", "name": ghosts, "rationale": "x"},
    ]}, cast.LIBRARY)
    assert [i["reason"] for i in invalid] == ["invalid: no title", "invalid: no rationale"]
    assert [(s["name"], s["title"]) for s in seats] == [("Pager lead", "Pager lead")]
    assert S.not_seated({"not_seated": [
        {"stakeholder": ghosts, "reason": "r"}, {"stakeholder": "Legal", "reason": ghosts},
    ]}) == []


def test_validate_gives_a_derived_seat_the_derived_style_and_drops_worker_extras():
    """A derived seat gets a persona the brief can always render: every field
    present (blank when unsaid), the fixed style, and nothing the worker added."""
    worker = {
        "role": "crew_owner", "title": "Crew lead", "rationale": "runs the crews",
        "style": "shouts in capitals", "nominated_by": "senior_director",
        "source": "library",
    }
    expected = [{
        "role": "crew_owner", "name": "Crew lead", "title": "Crew lead",
        "altitude": "", "goal": "", "ambition": "", "stake": "", "lens": "",
        "style": cast.DERIVED_STYLE, "rationale": "runs the crews", "source": "derived",
    }]

    doc, _ = S.parse(_answer({"seats": [worker]}))
    assert S.validate(doc, cast.LIBRARY) == (expected, [])
    # a raw dict that never went through parse is cleaned the same way
    assert S.validate({"seats": [worker]}, cast.LIBRARY) == (expected, [])
    assert S.validate(None, cast.LIBRARY) == ([], [])
    # a field that is not a string is unsaid, never its Python repr
    odd = dict(worker, name=["Crew"], lens={"a": 1}, goal=42, stake=None, altitude=True)
    assert S.validate({"seats": [odd]}, cast.LIBRARY) == (expected, [])


# --- not_seated ----------------------------------------------------------

def test_not_seated_drops_entries_without_a_stakeholder_and_a_reason():
    doc = {"not_seated": [
        {"stakeholder": "Legal", "reason": "no filing is involved", "represented_by": " privacy "},
        {"stakeholder": "Finance \u2014 FP&A", "reason": "x" * 500},
        {"stakeholder": "Support", "reason": "takes the calls", "represented_by": 7},
        {"stakeholder": "Legal ops"},
        {"reason": "nobody named"},
        {"stakeholder": "  ", "reason": "blank"},
        {"stakeholder": "\x00\u200b", "reason": "blank once cleaned"},
        {"stakeholder": 7, "reason": "numbers"},
        {"stakeholder": "Board", "reason": ["a list"]},
        "Legal",
        None,
    ]}

    assert S.not_seated(doc) == [
        {"stakeholder": "Legal", "reason": "no filing is involved", "represented_by": "privacy"},
        {"stakeholder": "Finance - FP&A", "reason": "x" * (S.REASON_MAX - 1) + "\u2026",
         "represented_by": None},
        {"stakeholder": "Support", "reason": "takes the calls", "represented_by": None},
    ]
    clipped = S.not_seated({"not_seated": [{"stakeholder": "y" * 500, "reason": "r"}]})
    assert clipped[0]["stakeholder"] == "y" * (S.STAKEHOLDER_MAX - 1) + "\u2026"
    assert S.not_seated(None) == [] and S.not_seated({"not_seated": "Legal"}) == []


# --- resolve -------------------------------------------------------------

SELECTORS = ("owner", "manager", "senior_director")
FIXED = ("owner", "senior_director", "manager", "junior_ic")
RECORD_KEYS = SEAT_KEYS | {"nominated_by"}
MANAGER = cast.CAST["manager"]["name"]
CHAIR = cast.CAST["senior_director"]["name"]


def _stages(*answers) -> list[dict]:
    """``s["stages"]`` as the playbook builds it, one kept take per stage.

    A dict is one seat-list block under a sentence of prose, a str is the
    whole answer and None is an undelivered take.
    """
    stages = []
    for n, answer in enumerate(answers, 1):
        if isinstance(answer, dict):
            answer = _answer(answer)
        doc, code = S.parse(answer)
        seats, _ = S.validate(doc, cast.LIBRARY)
        delivered = bool(answer)
        stages.append({
            "stage": n, "role": SELECTORS[n - 1], "delivered": delivered,
            "doc": doc, "code": S.stage_code(delivered, code, seats),
        })
    return stages


def _derived(role, title) -> dict:
    return _seat(role, title=title)


def _roles(seats) -> list[str]:
    return [s["role"] for s in seats]


def _by_stakeholder(considered) -> dict:
    return {c["stakeholder"]: c for c in considered}


def _considered(stakeholder, role, reason, represented_by=None) -> dict:
    return {
        "stakeholder": stakeholder, "role": role, "reason": reason,
        "represented_by": represented_by,
    }


def test_fixed_seats_are_the_four_fixed_records():
    """Nobody puts the fixed four forward: they are always at the table (Q5)."""
    fixed = S.fixed_seats()

    assert tuple(fixed) == FIXED
    for role, seat in fixed.items():
        assert seat == {
            **cast.CAST[role], "role": role, "rationale": cast.FIXED_RATIONALE[role],
            "nominated_by": "fixed", "source": "fixed",
        }
        assert set(seat) == RECORD_KEYS, role
        assert seat is not cast.CAST[role]
    again = S.fixed_seats()
    assert again == fixed and all(again[r] is not fixed[r] for r in FIXED)


def test_resolve_takes_the_chairs_list_as_authoritative():
    """Stage 3 is the committee. The owner's and the manager's lists only say
    who put a seat forward first, whatever they seated."""
    crew = _derived("crew_owner", "Crew lead")
    stages = _stages(
        {"seats": [_seat("security"), _seat("sre")]},
        {"seats": [_seat("security"), _seat("privacy")]},
        {"seats": [_seat("privacy"), _seat("tl"), crew, _seat("owner"), _seat("chair")]},
    )

    out = S.resolve(stages, cast.LIBRARY)

    assert set(out) == {
        "seated", "reviewers", "considered", "considered_dropped", "invalid_dropped", "fallback",
    }
    assert out["fallback"] is None
    assert out["considered_dropped"] == out["invalid_dropped"] == 0
    assert out["reviewers"] == ["senior_director", "manager", "privacy", "tl", "crew_owner"]
    assert _roles(out["seated"]) == [
        "owner", "senior_director", "manager", "privacy", "tl", "crew_owner", "junior_ic",
    ]
    fixed = S.fixed_seats()
    seated = {s["role"]: s for s in out["seated"]}
    for role in FIXED:
        assert seated[role] == fixed[role]
    assert seated["privacy"] == {
        "role": "privacy", **cast.LIBRARY["privacy"],
        "rationale": "privacy carries a risk in this proposal",
        "nominated_by": "manager", "source": "library",
    }
    assert seated["tl"]["nominated_by"] == "senior_director"
    assert seated["crew_owner"]["source"] == "derived"
    assert seated["crew_owner"]["title"] == "Crew lead"
    assert seated["crew_owner"]["style"] == cast.DERIVED_STYLE
    assert all(set(s) == RECORD_KEYS for s in out["seated"])
    # security and sre were put forward and the chair left them out
    assert {c["role"] for c in out["considered"]} == {"security", "sre"}


def test_resolve_never_falls_back_on_a_failed_earlier_stage():
    """A failed owner or manager costs the run nothing: the chair proposes
    from scratch and her list is seated. This covers a stage-1 block whose
    seats are a string, not a list (gap 3)."""
    chair = {"seats": [_seat("security"), _seat("tl")]}
    failures = [
        (None, "no_answer"),
        ("I would seat security and sre.", "no_block"),
        (_answer("{broken"), "unparseable"),
        ({"seats": "security"}, "too_few"),
        ({"seats": [_seat("owner"), _seat("Security")]}, "too_few"),
    ]
    for first, code in failures:
        stages = _stages(first, None, chair)
        assert [st["code"] for st in stages] == [code, "no_answer", None], first

        out = S.resolve(stages, cast.LIBRARY)

        assert out["fallback"] is None, first
        assert out["reviewers"] == ["senior_director", "manager", "security", "tl"], first
        assert {s["nominated_by"] for s in out["seated"][3:5]} == {"senior_director"}
    # a usable owner and a failed manager: the owner still gets the credit
    out = S.resolve(_stages({"seats": [_seat("tl")]}, "no block here", chair), cast.LIBRARY)
    assert out["fallback"] is None
    assert [s["nominated_by"] for s in out["seated"]][3:5] == ["senior_director", "owner"]
    # every JSON value a worker can put in an entry's fields: resolve never
    # raises, junk earlier lists change nothing, and a junk chair list falls back
    values = (None, True, 7, 1.5, "", "x", [], ["tl"], {}, {"a": 1}, "Legal")
    junk = {
        "seats": [{k: v for k in ("role", "title", "rationale", "name", "lens")}
                  for v in values],
        "not_seated": [{"stakeholder": v, "reason": v, "represented_by": v} for v in values],
    }
    out = S.resolve(_stages(junk, junk, chair), cast.LIBRARY)
    assert out["reviewers"] == ["senior_director", "manager", "security", "tl"]
    assert S.resolve(_stages(junk, junk, junk), cast.LIBRARY)["fallback"] == "too_few"


def test_resolve_falls_back_with_the_chairs_code():
    """A chair list that cannot seat anyone gives today's seven, and the code
    says why. An undelivered chair is reported as chair_failed."""
    assert S.stage_code(False, None, [{"role": "tpm"}]) == "no_answer"
    assert S.stage_code(False, "no_block", []) == "no_answer"
    assert S.stage_code(True, "no_block", []) == "no_block"
    assert S.stage_code(True, "unparseable", []) == "unparseable"
    assert S.stage_code(True, None, []) == "too_few"
    assert S.stage_code(True, None, [{"role": "tpm"}]) is None

    owner = {"seats": [_seat("tpm"), _seat("pm")]}  # both in the default seven
    chairs = [
        (None, "chair_failed"),
        ("I ratify the list above.", "no_block"),
        (_answer("[1, 2]"), "unparseable"),
        ({"seats": []}, "too_few"),
        ({"seats": "security"}, "too_few"),
        ({"seats": [_seat("owner"), _seat("chair"), _seat("manager")]}, "too_few"),
    ]
    for chair, fallback in chairs:
        out = S.resolve(_stages(owner, owner, chair), cast.LIBRARY)
        assert out == S.fallback(fallback), chair
    # no stage-3 entry at all is a chair who never answered
    assert S.resolve([], cast.LIBRARY) == S.fallback("chair_failed")
    assert S.resolve(_stages(owner), cast.LIBRARY) == S.fallback("chair_failed")
    # the chair's code is recomputed from her entry, never trusted: a stored
    # None over a list with no valid seat, or a bare entry, still falls back
    earlier = _stages(owner, owner)
    empty = {"stage": 3, "role": "senior_director", "delivered": True,
             "doc": {"seats": []}, "code": None}
    assert S.resolve([*earlier, empty], cast.LIBRARY) == S.fallback("too_few")
    assert S.resolve([*earlier, {"stage": 3}], cast.LIBRARY) == S.fallback("chair_failed")


def test_resolve_cuts_an_overflow_to_twelve_and_names_a_seated_representative():
    """Fifteen valid seats: the first ten join senior_director and manager,
    and the last five are considered, each represented by someone seated
    (Q4). A chair note keyed "security" names security's representative; a
    note keyed "security team" is a different stakeholder. A list of any
    length is read in linear time and still seats twelve."""
    seated_ten = [
        _seat("tpm"), _seat("pm"), _seat("tl"), _seat("staff_ic"), _seat("data_scientist"),
        _seat("sre"), _seat("privacy"), _seat("partner_owner"),
        _derived("crew_owner", "Crew lead"), _derived("fleet_ops", "Fleet operations lead"),
    ]
    overflow = [
        _seat("security"), _derived("billing", "Billing lead"), _derived("legal", "Counsel"),
        _derived("support", "Support lead"), _derived("growth", "Growth PM"),
    ]
    notes = [
        {"stakeholder": "Security", "reason": "covered", "represented_by": "privacy"},
        {"stakeholder": "Security team", "reason": "one voice is enough", "represented_by": "tpm"},
        {"stakeholder": "Billing", "reason": "later", "represented_by": "nobody"},
        {"stakeholder": "legal ", "reason": "later", "represented_by": "security"},
    ]
    chair = {"seats": seated_ten + overflow, "not_seated": notes}

    out = S.resolve(_stages(None, None, chair), cast.LIBRARY)

    assert out["fallback"] is None
    assert len(out["reviewers"]) == S.MAX_REVIEWERS == 12
    assert out["reviewers"] == ["senior_director", "manager", *_roles(seated_ten)]
    assert _roles(out["seated"]) == ["owner", *out["reviewers"], "junior_ic"]
    over = "over the 12-seat bound"
    assert _by_stakeholder(out["considered"]) == {
        "Security Engineer": _considered("Security Engineer", "security", over, "privacy"),
        "Billing lead": _considered("Billing lead", "billing", over, "senior_director"),
        # "legal " is keyed "legal", but it names an unseated representative
        "Counsel": _considered("Counsel", "legal", over, "senior_director"),
        "Support lead": _considered("Support lead", "support", over, "senior_director"),
        "Growth PM": _considered("Growth PM", "growth", over, "senior_director"),
        "Security team": _considered("Security team", None, "one voice is enough", "tpm"),
    }
    seated = set(_roles(out["seated"]))
    assert all(c["represented_by"] in seated for c in out["considered"])
    # only the chair's own note names an overflow seat's representative
    # (rule 4): the owner's note on support, pointing at a seated tpm, does not
    owner = {"seats": [_seat("tl")], "not_seated": [
        {"stakeholder": "Support", "reason": "the owner's view", "represented_by": "tpm"},
    ]}
    again = S.resolve(_stages(owner, None, chair), cast.LIBRARY)
    assert _by_stakeholder(again["considered"]) == _by_stakeholder(out["considered"])

    # 20 000 valid seats on every stage: twelve seated, the first 40 of the
    # rest considered and the others counted, and no pairwise work (a list
    # scan per seat would take minutes here)
    many = {"seats": [_derived(f"d{i}", f"Lead {i}") for i in range(20_000)]}
    stages = _stages(many, many, many)
    start = time.perf_counter()
    out = S.resolve(stages, cast.LIBRARY)
    assert time.perf_counter() - start < 2.0
    assert out["reviewers"] == ["senior_director", "manager", *(f"d{i}" for i in range(10))]
    assert S.CONSIDERED_MAX == 40
    assert _roles(out["considered"]) == [f"d{i}" for i in range(10, 50)]
    assert out["considered_dropped"] == 20_000 - 10 - 40
    assert {c["represented_by"] for c in out["considered"]} == {"senior_director"}
    assert S.resolve(stages, cast.LIBRARY) == out  # the same lists, the same committee


def test_resolve_credits_the_earliest_stage_that_listed_a_seat():
    """nominated_by is the master's to compute: the first selector whose valid
    list held the slug. A worker's own nominated_by never survives."""
    stages = _stages(
        {"seats": [_seat("security"), _seat("sre"), {"role": "tl"}]},  # tl: no rationale
        {"seats": [_seat("privacy"), _seat("security"), _seat("tl")]},
        {"seats": [
            _seat("tl"), _seat("privacy"), _seat("security"), _seat("sre"),
            _derived("crew_owner", "Crew lead"),
        ]},
    )
    stages[2]["doc"]["seats"][4]["nominated_by"] = "owner"  # a raw doc, never parsed

    out = S.resolve(stages, cast.LIBRARY)

    assert {s["role"]: s["nominated_by"] for s in out["seated"]} == {
        "owner": "fixed", "senior_director": "fixed", "manager": "fixed",
        "tl": "manager", "privacy": "manager", "security": "owner", "sre": "owner",
        "crew_owner": "senior_director", "junior_ic": "fixed",
    }
    assert out["considered"] == []


def test_resolve_collects_considered_from_every_source():
    """Everyone named and not seated is on the record with a reason: a note, a
    seat a later list dropped, an invalid entry, or a seat the default
    committee has no room for."""
    stages = _stages(
        {"seats": [_seat("security"), _seat("sre"), _seat("Finance")],
         "not_seated": [{"stakeholder": "Legal", "reason": "no filing is involved",
                         "represented_by": "privacy"}]},
        {"seats": [_seat("security"), _seat("privacy"), {"role": "crew_owner", "rationale": "x"}],
         "not_seated": [{"stakeholder": "Support", "reason": "takes the calls later",
                         "represented_by": "tpm"}]},
        {"seats": [_seat("security"), _seat("tl")],
         "not_seated": [{"stakeholder": "Privacy", "reason": "security covers the data flow",
                         "represented_by": "security"}]},
    )

    out = S.resolve(stages, cast.LIBRARY)

    assert _roles(out["seated"]) == [
        "owner", "senior_director", "manager", "security", "tl", "junior_ic",
    ]
    assert _by_stakeholder(out["considered"]) == {
        "Finance": _considered("Finance", None, "invalid: bad slug"),
        # privacy is not seated, so Legal has no representative
        "Legal": _considered("Legal", None, "no filing is involved"),
        "Site Reliability Engineer, on-call": _considered(
            "Site Reliability Engineer, on-call", "sre", f"dropped by {MANAGER}"),
        "crew_owner": _considered("crew_owner", "crew_owner", "invalid: no title"),
        "Support": _considered("Support", None, "takes the calls later"),
        # the chair's note keyed "privacy" is the reason the seat was dropped
        "Privacy Engineer": _considered(
            "Privacy Engineer", "privacy", "security covers the data flow", "security"),
    }

    # a fallback: the stage 1-2 seats the default seven leave out are
    # considered, and a note may name a default reviewer as its representative
    stages = _stages(
        {"seats": [_seat("security"), _seat("tpm")],
         "not_seated": [{"stakeholder": "Legal", "reason": "no filing", "represented_by": "tpm"}]},
        None,
        _answer("{broken"),
    )

    out = S.resolve(stages, cast.LIBRARY)

    assert out["fallback"] == "unparseable"
    assert out["seated"] == S.fallback("unparseable")["seated"]
    assert _by_stakeholder(out["considered"]) == {
        "Security Engineer": _considered(
            "Security Engineer", "security",
            "not in the default committee (fallback: unparseable)"),
        "Legal": _considered("Legal", None, "no filing", "tpm"),
    }

    # a fallback reads stages 1-2 only (D2), so the chair's invalid entry and
    # note are not on the record; a seat the manager's usable list dropped
    # keeps its dropper, and only an undropped one is "not in the default"
    stages = _stages(
        {"seats": [_seat("security"), _seat("tpm")]},
        {"seats": [_seat("sre")]},
        {"seats": [_seat("Legal")],
         "not_seated": [{"stakeholder": "Finance", "reason": "no spend", "represented_by": "tpm"}]},
    )

    out = S.resolve(stages, cast.LIBRARY)

    assert out["fallback"] == "too_few"
    assert _by_stakeholder(out["considered"]) == {
        "Security Engineer": _considered(
            "Security Engineer", "security", f"dropped by {MANAGER}"),
        "Site Reliability Engineer, on-call": _considered(
            "Site Reliability Engineer, on-call", "sre",
            "not in the default committee (fallback: too_few)"),
    }


def test_resolve_matches_considered_entries_on_their_keys():
    """Rule 6: one entry per key (a seat's slug, a note's stakeholder
    lowercased) and the latest stage wins. A seated slug is never considered,
    even when an earlier stage listed it invalidly. A dropped seat's dropper
    is the first later stage with a usable list that leaves it out."""
    owner = {"seats": [{"role": "sre"}, _seat("privacy")]}  # sre has no rationale
    chair = {"seats": [_seat("security"), _seat("sre")]}

    # the manager's usable list leaves privacy out and says nothing about it
    out = S.resolve(_stages(owner, {"seats": [_seat("security")]}, chair), cast.LIBRARY)

    assert out["reviewers"] == ["senior_director", "manager", "security", "sre"]
    assert out["considered"] == [
        _considered("Privacy Engineer", "privacy", f"dropped by {MANAGER}"),
    ]

    # the manager fails, undelivered or delivered with no usable list, so the
    # chair's omission is the dropper; her note keyed "privacy team" is another
    # stakeholder
    notes = [{"stakeholder": "Privacy team", "reason": "no data moves", "represented_by": "sre"}]
    failed = [
        (None, "no_answer"),
        ("No list from me.", "no_block"),
        (_answer("{broken"), "unparseable"),
        ({"seats": [_seat("manager")]}, "too_few"),
    ]
    for manager, code in failed:
        stages = _stages(owner, manager, {**chair, "not_seated": notes})
        assert stages[1]["code"] == code

        out = S.resolve(stages, cast.LIBRARY)

        assert _by_stakeholder(out["considered"]) == {
            "Privacy Engineer": _considered("Privacy Engineer", "privacy", f"dropped by {CHAIR}"),
            "Privacy team": _considered("Privacy team", None, "no data moves", "sre"),
        }, code

    # a bad slug is keyed on its raw role lowercased: "Security" is the seated
    # security, so it is not considered, and "Finance" is the chair's note
    # keyed "finance", which replaces it
    invalid = {"seats": [_seat("Security"), _seat("Finance")]}
    noted = {**chair, "not_seated": [{"stakeholder": "finance", "reason": "no spend"}]}
    out = S.resolve(_stages(invalid, None, noted), cast.LIBRARY)

    assert out["considered"] == [_considered("finance", None, "no spend")]

    # a later note on the same key replaces an earlier one, and gives the
    # dropped seat its reason; a note keyed on a seated slug is dropped
    manager = {"seats": [_seat("security")], "not_seated": [
        {"stakeholder": " PRIVACY ", "reason": "security reads the data flow",
         "represented_by": "security"},
        {"stakeholder": "Security", "reason": "already here", "represented_by": "security"},
    ]}
    first = {**owner, "not_seated": [{"stakeholder": "privacy", "reason": "stale"}]}
    out = S.resolve(_stages(first, manager, chair), cast.LIBRARY)

    assert out["considered"] == [
        _considered("Privacy Engineer", "privacy", "security reads the data flow", "security"),
    ]


def test_resolve_caps_the_invalid_and_considered_lists():
    """A block of any size writes a bounded record to the reduction and the
    thread: each stage keeps its first 20 invalid entries and the committee
    its first 40 considered, in the usual order, and the result counts what
    was cut, so nothing vanishes silently."""
    assert (S.INVALID_MAX, S.CONSIDERED_MAX) == (20, 40)
    bad = [_seat(f"Bad{i}") for i in range(25)]
    notes = [{"stakeholder": f"Note {i}", "reason": "later"} for i in range(60)]

    # the chair's 25 bad slugs: the first 20 are considered, 5 are counted
    out = S.resolve(_stages(None, None, {"seats": [_seat("tl"), *bad]}), cast.LIBRARY)
    assert out["fallback"] is None and out["reviewers"][2:] == ["tl"]
    assert [c["stakeholder"] for c in out["considered"]] == [f"Bad{i}" for i in range(20)]
    assert (out["invalid_dropped"], out["considered_dropped"]) == (5, 0)

    # the chair's 60 notes: the first 40 are considered, 20 are counted
    out = S.resolve(_stages(None, None, {"seats": [_seat("tl")], "not_seated": notes}),
                    cast.LIBRARY)
    assert [c["stakeholder"] for c in out["considered"]] == [f"Note {i}" for i in range(40)]
    assert (out["invalid_dropped"], out["considered_dropped"]) == (0, 20)

    # a fallback caps the earlier stages' record the same way: 20 invalid
    # entries and 20 notes fill the 40; 5 invalid per stage and 40 more are counted
    owner = {"seats": bad, "not_seated": notes}
    out = S.resolve(_stages(owner, owner, None), cast.LIBRARY)
    assert out["seated"] == S.fallback("chair_failed")["seated"]
    assert [c["stakeholder"] for c in out["considered"]] == [
        *(f"Bad{i}" for i in range(20)), *(f"Note {i}" for i in range(20)),
    ]
    assert (out["invalid_dropped"], out["considered_dropped"]) == (10, 40)


def test_resolve_nulls_a_representative_who_is_not_seated():
    """Outside the overflow rule a representative must be a seated slug; an
    unseated one, a sentinel or a non-string becomes null."""
    notes = [
        {"stakeholder": "Legal", "reason": "a", "represented_by": "privacy"},
        {"stakeholder": "Finance", "reason": "b", "represented_by": "manager"},
        {"stakeholder": "Support", "reason": "c", "represented_by": "security"},
        {"stakeholder": "Board", "reason": "d", "represented_by": "chair"},
        {"stakeholder": "Ops", "reason": "e", "represented_by": " security "},
        {"stakeholder": "Growth", "reason": "f", "represented_by": 7},
        {"stakeholder": "Sales", "reason": "g", "represented_by": "Security"},
    ]
    owner = {"seats": [_seat("tpm")],
             "not_seated": [{"stakeholder": "Billing", "reason": "h", "represented_by": "tpm"}]}

    out = S.resolve(_stages(owner, None, {"seats": [_seat("security")], "not_seated": notes}),
                    cast.LIBRARY)

    reps = {c["stakeholder"]: c["represented_by"] for c in out["considered"]}
    assert reps == {
        "Legal": None, "Finance": "manager", "Support": "security", "Board": None,
        "Ops": "security", "Growth": None, "Sales": None,
        # the chair dropped tpm, so the owner's note has no one to point at
        "Billing": None, "Technical Program Manager": None,
    }


def test_fallback_never_raises_and_is_the_default_committee(monkeypatch):
    """Rule 7: the fixed four plus today's five reviewers, in CAST order. It
    reads no stage data, and a failure while collecting the considered list
    on a fallback leaves that list empty instead of costing the committee."""
    fixed = S.fixed_seats()
    for code in ("chair_failed", "no_block", "unparseable", "too_few"):
        out = S.fallback(code)

        assert out["fallback"] == code and out["considered"] == []
        assert out["considered_dropped"] == out["invalid_dropped"] == 0
        assert out["reviewers"] == list(cast.SENIORITY)
        assert _roles(out["seated"]) == list(cast.CAST)
        for seat in out["seated"]:
            role = seat["role"]
            assert set(seat) == RECORD_KEYS, role
            if role in fixed:
                assert seat == fixed[role]
            else:
                assert seat == {
                    **cast.CAST[role],
                    "rationale": f"default committee (selection fell back: {code})",
                    "nominated_by": "default", "source": "library",
                }

    stages = _stages({"seats": [_seat("security")]}, None, "no block")

    def boom(*args, **kwargs):
        raise RuntimeError("validate broke")

    monkeypatch.setattr(S, "validate", boom)
    monkeypatch.setattr(S, "not_seated", boom)
    assert S.fallback("too_few")["reviewers"] == list(cast.SENIORITY)  # no stage data read
    assert S.resolve(stages, cast.LIBRARY) == S.fallback("no_block")


def test_seat_records_are_new_dicts():
    """A seat record is built, never borrowed: changing one cannot touch the
    cast or the library, and no two calls share a dict."""
    before = json.dumps({"cast": cast.CAST, "library": cast.LIBRARY}, sort_keys=True)
    borrowed = {id(p) for p in (*cast.CAST.values(), *cast.LIBRARY.values())}
    stages = _stages(
        {"seats": [_seat("tpm"), _seat("security")]},
        {"seats": [_seat("security"), _derived("crew_owner", "Crew lead")]},
        {"seats": [_seat("tpm"), _seat("security"), _derived("crew_owner", "Crew lead")]},
    )

    results = [
        S.resolve(stages, cast.LIBRARY), S.resolve(stages, cast.LIBRARY),
        S.fallback("too_few"), S.fallback("too_few"),
    ]

    records = [seat for out in results for seat in out["seated"]]
    records += list(S.fixed_seats().values())
    assert len({id(r) for r in records}) == len(records)
    assert not {id(r) for r in records} & borrowed
    for record in records:
        record["name"] = "changed"
        record["stake"] = "changed"
    assert json.dumps({"cast": cast.CAST, "library": cast.LIBRARY}, sort_keys=True) == before
