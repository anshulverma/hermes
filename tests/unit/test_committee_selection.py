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
