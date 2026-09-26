"""The committee's voice rules and the measurement of one turn (voice.py)."""
from __future__ import annotations

import json
import time

import pytest

from playbooks.committee import turnblock, voice


# --- T1: measure ------------------------------------------------------------

def test_measure_counts_words_and_keeps_every_key_eval_reads():
    m = voice.measure("Defer it. The staffing line is fiction.")
    assert {"words", "pointers", "examples", "longest_paragraph_words", "filler_hits"} <= set(m)
    assert m["words"] == 7
    assert m["sentences"] == 2
    assert m["lines"] == 1
    assert m["first_line_words"] == 7
    assert m["cap"] == 150 and m["rules_version"] == voice.RULES_VERSION


def test_a_fenced_snippet_breaks_no_formatting_rule_and_adds_no_words():
    body = "Look at this.\n\n```python\n# x\nf(**kw)\n- y\n| a |\n|---|---|\n```\n"
    m = voice.measure(body)
    assert m["words"] == 3
    for key in ("headers", "bold", "bullets", "nested_bullets", "tables", "dashes"):
        assert m[key] == 0, key
    assert m["fenced_lines"] == 5
    assert m["examples"] == 1  # the fenced block itself


def test_an_unclosed_fence_is_prose():
    m = voice.measure("```\n# a header\n")
    assert m["headers"] == 1
    assert m["fenced_lines"] == 0


def test_fences_close_on_a_long_enough_line_of_their_own_marker_and_can_follow_each_other():
    two = voice.measure("```\na\n```\n```\nb\n```")
    assert (two["fenced_lines"], two["words"]) == (2, 0)
    tilde = voice.measure("~~~\n# x\n~~~")
    assert (tilde["fenced_lines"], tilde["headers"]) == (1, 0)
    # a closer shorter than its opener is a fenced line, not the end of the fence
    short = voice.measure("````\n# x\n```\ny\n````")
    assert (short["fenced_lines"], short["words"], short["headers"]) == (3, 0, 0)
    assert voice.measure("Fine.\n```\n§2 and section 3\n```")["pointers_section"] == 0


def test_dashes_count_unless_quoted_or_in_code():
    m = voice.measure('Ship it — now. Pages 3–5. "a — b" and `x – y`.')
    assert (m["em_dashes"], m["en_dashes"], m["dashes"]) == (1, 1, 2)
    assert voice.measure("“quoted — dash” here.")["dashes"] == 0
    # C2: a curly quote runs to the next closing one on its line, whatever opens inside it
    assert voice.measure("Ship “a — “b” c” now.")["dashes"] == 0
    assert voice.measure("Ship “a — then “b” now.")["dashes"] == 0
    assert voice.measure("Ship “a — b\nthen “c — d” now.")["dashes"] == 1


@pytest.mark.parametrize("text, bold", [
    ("This is **really** bad.", 1),
    ("__really important__ says so.", 1),
    ("__a\nb__ c.", 1),
    ("Call `f(**kwargs)` or foo(**kwargs, **extra) today.", 0),
    ("Run __main__ now.", 0),
    ("call __init__, then stop.", 0),
    ("See playbooks/committee/__init__.py:11 for it.", 0),
])
def test_bold_ignores_kwargs_and_dunder_names(text, bold):
    assert voice.measure(text)["bold"] == bold


def test_the_init_path_is_a_pointer_not_bold():
    m = voice.measure("See playbooks/committee/__init__.py:11 for it.")
    assert m["bold"] == 0 and m["pointers_path_line"] == 1


def test_headers_tables_and_bullets_numbered_and_nested():
    body = (
        "## Heading\n"
        "| a | b |\n"
        "|---|---|\n"
        "- one\n"
        "2. two\n"
        "3) three\n"
        "  - nested\n"
        "\t* tabbed\n"
    )
    m = voice.measure(body)
    assert m["headers"] == 1
    assert m["tables"] == 1
    assert m["bullets"] == 5
    assert m["nested_bullets"] == 2
    assert voice.measure("  |---|---|  ")["tables"] == 1


def test_pointers_and_sentences():
    m = voice.measure("See engine/dispatch.py:116-132 and §2.1 for the loop.")
    assert m["sentences"] == 1
    assert m["pointers"] == 2
    assert (m["pointers_path_line"], m["pointers_section"]) == (1, 1)
    assert voice.measure("Updated §4.2.")["sentences"] == 1
    assert voice.measure("Section 3 is thin, e.g. the dates.")["sentences"] == 1


def test_examples_count_phrases_code_fences_and_units():
    m = voice.measure("For example 50% of runs, such as `x`, take 3 s and 2x the 50%. memory.")
    # 'for example', 'such as', one inline code span, 50%, 3 s, 2x, 50%.
    assert m["examples"] == 7


def test_tells_and_filler_hits():
    body = (
        "I checked the doc. As turn 5 said, the original is unchanged. "
        "That said, rather than this, delve in."
    )
    m = voice.measure(body)
    assert m["tells"] == {"process": 1, "turn_refs": 1, "unchanged": 1, "preempt": 1, "filler": 2}
    assert m["filler_hits"] == 6


def test_longest_paragraph_words():
    assert voice.measure("one two three\n\nfour five\nsix seven")["longest_paragraph_words"] == 4


def test_image_lines_add_no_words():
    body = (
        "Staffing is the risk.\n"
        "![staffing curve](images/t02-owner.svg)\n"
        "Description: engineers per week against the plan, flat after week 6.\n"
        "Figure: the pipeline\n"
        "```mermaid\ngraph TD; A-->B\n```\n"
        "Description: two stages.\n"
        "Inline ![x](images/t02-owner.png) here too."
    )
    m = voice.measure(body)
    assert m["words"] == 7  # "Staffing is the risk." + "Inline here too."
    assert [im["kind"] for im in m["images"]] == ["image", "mermaid", "image"]
    assert m["images"][0]["description"].startswith("engineers per week")
    assert m["images"][1]["caption"] == "the pipeline"
    assert m["images"][2]["description"] == ""
    assert m["images_uncaptioned"] == 1


def test_measure_never_raises():
    for junk in (None, "", "```", "![", "![x](", "\x00", 5):
        voice.measure(junk)  # type: ignore[arg-type]
    # measure runs master-side on every take, so a stuck or crafted body must not
    # go quadratic: each of these took seconds to minutes when a pattern rescanned
    # the line from every opener.
    shrinking_openers = "\n".join("`" * n for n in range(300, 2, -1)) + "\n" + "a\n" * 50_000
    # U+1D1D shares its low byte with the closing curly quote, so str.find
    # cannot skip ahead: a scan from every unclosed opener would show here.
    unclosed_curly = "\u201c\u1d1d" * 100_000
    for body in ("![" * 30_000, "![a](" * 12_000, " __" + "a " * 30_000, "```x\n" * 12_000,
                 "“a" * 30_000, "![c](images/x.svg)\nDescription: a" + " " * 60_000 + "b",
                 " " * 60_000 + "x", "\t" * 60_000 + "x", shrinking_openers, unclosed_curly):
        start = time.perf_counter()
        voice.measure(body)
        voice.segments(body)
        assert time.perf_counter() - start < 2.0, body[:12]


# --- T2: violations, flags, note, summary -----------------------------------

def _m(**over):
    base = voice.measure("Defer it: `engine/dispatch.py:1` for example.")
    base.update(over)
    return base


@pytest.mark.parametrize("role, over, slug", [
    ("tl", {"words": 151}, "over_cap"),
    ("chair", {"words": 301}, "over_cap"),
    ("junior_ic", {"words": 41}, "over_cap"),
    ("junior_ic", {"lines": 2}, "multi_line"),
    ("junior_ic", {"sentences": 2}, "multi_sentence"),
    ("tl", {"headers": 1}, "headers"),
    ("tl", {"bold": 1}, "bold"),
    ("tl", {"tables": 1}, "tables"),
    ("tl", {"nested_bullets": 1}, "nested"),
    ("tl", {"bullets": 6}, "too_many_bullets"),
    ("chair", {"bullets": 9}, "too_many_bullets"),
    ("tl", {"images": [{"kind": "mermaid", "ok": True}] * 2}, "too_many_images"),
    ("junior_ic", {"images": [{"kind": "mermaid", "ok": True}]}, "too_many_images"),
    ("chair", {"images": [{"kind": "mermaid", "ok": True}]}, "too_many_images"),
    ("tl", {"images_uncaptioned": 1}, "image_uncaptioned"),
    ("tl", {"images": [{"kind": "image", "ok": False}]}, "image_missing"),
    ("owner", {"action_chars": turnblock.ACTION_MAX + 1}, "action_too_long"),
])
def test_each_hard_rule_is_its_own_violation(role, over, slug):
    assert voice.violations(_m(**over), role) == [slug]


def test_a_compliant_turn_breaks_nothing_and_the_limits_are_inclusive():
    assert voice.violations(_m(words=150, bullets=5), "tl") == []
    assert voice.violations(_m(words=300, bullets=8), "chair") == []
    assert voice.violations(_m(action_chars=turnblock.ACTION_MAX), "owner") == []
    assert voice.violations(_m(action_chars=999), "tl") == []  # owner only


def test_a_two_sentence_one_line_junior_report_is_multi_sentence():
    m = voice.measure("I added the rollback plan. It is in section 4.", "junior_ic")
    assert voice.violations(m, "junior_ic") == ["multi_sentence"]


def test_flags_are_soft_and_role_scoped():
    m = voice.measure("Defer it — " + "word " * 30)
    assert voice.flags(m, "tl") == ["no_pointer", "no_example", "dashes", "long_first_line"]
    assert voice.flags(m, "junior_ic") == ["dashes", "long_first_line"]
    assert voice.flags(_m(stance_chars=201), "chair") == ["stance_clipped"]
    assert voice.violations(m, "tl") == []


def test_roles_caps_and_cap_text():
    assert voice.cap_for("security") == 150
    assert voice.kind("security") == "reviewer"
    assert [voice.cap_text(r) for r in ("tl", "owner", "junior_ic", "chair")] == [
        "150 words", "150 words", "one sentence of 40 words or fewer", "300 words"]
    assert voice.MAX_TAKES == 3 and voice.RETAKE_NOTE_MAX == 200
    assert voice.IMAGE_MAX_BYTES == 2 * 1024 * 1024


def test_every_rules_line_is_one_plain_line():
    assert voice.RULES
    for line in voice.RULES:
        assert "\n" not in line and not line.startswith("#"), line
        assert "**" not in line and "—" not in line and "–" not in line, line
    joined = "\n".join(voice.RULES)
    assert "Bad:" in joined and "Good:" in joined


def test_note_phrases_each_slug_image_rules_first():
    m = _m(words=212, bold=3, cap=150)
    assert voice.note(m, ["over_cap", "bold"], take=2) == (
        "Retake 2 of 3. Rules broken: 212 words (cap 150); 3 bold. Say it again within them."
    )
    # Six rules at once still fit the clip whole, every one named and the
    # instruction last; the image rules lead, so a longer list loses a count
    # the speaker can see by rereading, never an image check made master-side.
    six = voice.note(_m(words=212, headers=2, bold=3, nested_bullets=2, cap=150), [
        "over_cap", "headers", "bold", "nested", "image_uncaptioned", "image_missing"], take=3)
    assert six == (
        "Retake 3 of 3. Rules broken: an image without its caption or description; "
        "an image missing or not your own file; 212 words (cap 150); 2 headers; 3 bold; "
        "2 nested bullets. Say it again within them."
    )
    from playbooks.committee import cast
    assert cast.clip(six, voice.RETAKE_NOTE_MAX) == six
    every = _m(words=400, lines=3, sentences=4, headers=1, bold=2, tables=1,
               nested_bullets=2, bullets=9, images=[{}, {}], action_chars=250, kind="chair")
    said = voice.note(every, [
        "over_cap", "multi_line", "multi_sentence", "headers", "bold", "tables", "nested",
        "too_many_bullets", "too_many_images", "image_uncaptioned", "image_missing",
        "action_too_long"], take=3)
    for phrase in ("400 words (cap", "3 lines (one allowed)", "4 sentences (one allowed)",
                   "1 headers", "2 bold", "1 tables", "2 nested bullets", "9 bullets (max 8)",
                   "2 images (max 0)", "an image without its caption or description",
                   "an image missing or not your own file",
                   "action 250 characters (max 200)"):
        assert phrase in said, phrase
    assert len(cast.clip(said, voice.RETAKE_NOTE_MAX)) <= voice.RETAKE_NOTE_MAX


def _v(words, **over):
    doc = {"words": words, "cap": 150, "lines": 1, "sentences": 1, "first_line_words": 5,
           "bold": 0, "headers": 0, "tables": 0, "nested_bullets": 0, "dashes": 0,
           "pointers": 1, "tells": {"turn_refs": 0, "unchanged": 0}}
    doc.update(over)
    return doc


def test_summary_applies_each_formula():
    rows = [
        ("turn", {"role": "tl", "voice": _v(100), "takes": 2, "violations": []}),
        ("turn", {"role": "owner", "voice": _v(200, first_line_words=30, bold=1)}),
        ("turn", {"role": "pm", "voice": _v(120, pointers=0, dashes=2,
                                             tells={"turn_refs": 3, "unchanged": 0})}),
        ("turn", {"role": "junior_ic", "voice": _v(12, cap=40,
                                                    tells={"turn_refs": 0, "unchanged": 1})}),
        ("turn", {"role": "junior_ic", "voice": _v(50, cap=40, sentences=2)}),
        ("turn", {"role": "tpm", "voice": None}),  # undelivered: left out
        ("take", {"role": "tl", "voice": _v(900)}),  # a discarded take: left out
        ("selection", {"voice": _v(900)}),
        ("one_on_one", {"voice": _v(900)}),
        ("decision", {"voice": _v(280, cap=300, headers=0, tables=0), "takes": 3,
                      "violations": ["bold"]}),
    ]
    s = voice.summary(rows)
    assert s == {
        "owner_reviewer_median_words": 120.0,
        "owner_reviewer_pct_within_cap": 66.7,
        "median_words_by_role": {"tl": 100.0, "owner": 200.0, "pm": 120.0,
                                 "junior_ic": 31.0, "chair": 280.0},
        "chair_words": 280, "chair_headers": 0, "chair_tables": 0,
        "junior_turns": 2,
        "junior_pct_compliant": 50.0,
        "pct_clean_format": 83.3,
        "pct_first_line_le_25": 66.7,
        "unquoted_dashes": 2,
        "reviewer_pct_with_pointer": 50.0,
        "max_turn_refs": 3,
        "unchanged_mentions_junior_chair": 1,
        "total_takes": 9,
        "retakes_by_role": {"tl": 1, "owner": 0, "pm": 0, "junior_ic": 0, "chair": 2},
        "kept_flagged": 1,
    }


def test_summary_is_null_before_voice_and_percentages_null_on_empty_populations():
    assert voice.summary([("turn", {"role": "tl"}), ("decision", {"verdict": "x"})]) is None
    only_chair = voice.summary([("decision", {"voice": _v(10, cap=300)})])
    assert only_chair["owner_reviewer_median_words"] is None
    assert only_chair["owner_reviewer_pct_within_cap"] is None
    assert only_chair["junior_pct_compliant"] is None
    assert only_chair["reviewer_pct_with_pointer"] is None
    assert only_chair["pct_clean_format"] == 100.0


def test_summary_reads_a_number_it_cannot_trust_as_absent():
    """A hand-edited row never raises out of the view route or eval, and never
    puts NaN in a payload served with allow_nan=False: a junk count is 0, a
    junk cap is the default cap, a junk chair number is None."""
    nan, inf = float("nan"), float("inf")
    rows = [
        ("turn", {"role": "tl", "voice": _v("many", cap="x", dashes="x", tells=[1])}),
        ("turn", {"role": "owner", "voice": _v(nan, first_line_words=inf, bold=True,
                                                tells={"turn_refs": "x", "unchanged": nan})}),
        ("turn", {"role": "pm", "voice": _v([1], pointers=10**400, dashes=2.0, bold=1)}),
        ("turn", {"role": "junior_ic", "voice": _v(12, cap=40,
                                                    tells={"turn_refs": 2, "unchanged": "x"})}),
        ("decision", {"voice": _v("x", cap=300, headers=nan, tables=True,
                                  tells={"turn_refs": nan, "unchanged": 1})}),
    ]
    s = voice.summary(rows)
    json.dumps(s, allow_nan=False)
    assert s == {
        "owner_reviewer_median_words": 0.0,
        "owner_reviewer_pct_within_cap": 100.0,
        "median_words_by_role": {"tl": 0.0, "owner": 0.0, "pm": 0.0,
                                 "junior_ic": 12.0, "chair": 0.0},
        "chair_words": None, "chair_headers": None, "chair_tables": None,
        "junior_turns": 1,
        "junior_pct_compliant": 100.0,
        "pct_clean_format": 80.0,
        "pct_first_line_le_25": 100.0,
        "unquoted_dashes": 2,
        "reviewer_pct_with_pointer": 50.0,
        "max_turn_refs": 2,
        "unchanged_mentions_junior_chair": 1,
        "total_takes": 5,
        "retakes_by_role": {"tl": 0, "owner": 0, "pm": 0, "junior_ic": 0, "chair": 0},
        "kept_flagged": 0,
    }


# --- T3: the image grammar and check_images ---------------------------------

def _img(body):
    return voice.measure(body)["images"]


def _dir(tmp_path):
    d = tmp_path / "images"
    d.mkdir()
    return d


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"></svg>'
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_own_svg_and_png_are_ok(tmp_path):
    d = _dir(tmp_path)
    (d / "t02-owner.svg").write_bytes(b"\xef\xbb\xbf  " + SVG)
    (d / "t04-tl.png").write_bytes(PNG)
    svg = voice.check_images(_img("![c](images/t02-owner.svg)\nDescription: d"), d, "t02-owner")
    png = voice.check_images(_img("![c](images/t04-tl.png)\nDescription: d"), d, "t04-tl")
    assert svg[0]["ok"] is True and png[0]["ok"] is True
    (d / "t02-owner.svg").write_bytes(b'<?xml version="1.0"?>\n' + SVG)
    prolog = voice.check_images(_img("![c](images/t02-owner.svg)\nDescription: d"), d, "t02-owner")
    assert prolog[0]["ok"] is True


@pytest.mark.parametrize("prepare", ["missing", "symlink", "oversize", "badmagic", "foreign"])
def test_a_bad_file_image_is_not_ok(tmp_path, prepare):
    d = _dir(tmp_path)
    target = d / "t02-owner.svg"
    if prepare == "symlink":
        (tmp_path / "real.svg").write_bytes(SVG)
        target.symlink_to(tmp_path / "real.svg")
    elif prepare == "oversize":
        target.write_bytes(SVG + b" " * voice.IMAGE_MAX_BYTES)
    elif prepare == "badmagic":
        target.write_bytes(b"GIF89a")
    elif prepare == "foreign":
        target.write_bytes(SVG)
        (d / "t04-tl.svg").write_bytes(SVG)
    body = "![c](images/t04-tl.svg)" if prepare == "foreign" else "![c](images/t02-owner.svg)"
    images = voice.check_images(_img(body + "\nDescription: d"), d, "t02-owner")
    assert images[0]["ok"] is False
    assert voice.violations({"images": images}, "owner") == ["image_missing"]


def test_the_reference_must_be_exactly_images_slash_name(tmp_path):
    d = _dir(tmp_path)
    (d / "t02-owner.svg").write_bytes(SVG)
    bare = voice.check_images(_img("![c](t02-owner.svg)\nDescription: d"), d, "t02-owner")
    assert bare[0]["name"] == "t02-owner.svg" and bare[0]["ref"] == "t02-owner.svg"
    assert bare[0]["ok"] is False


def test_http_and_reference_style_images_are_split_out_and_never_ok(tmp_path):
    d = _dir(tmp_path)
    own_line = voice.segments("Look.\n![chart](http://evil.example/x.png)\nDescription: d")
    inline = voice.segments("See ![x](http://evil.example/y.png) mid-sentence.")
    ref_style = voice.segments("![chart][fig1]\nDescription: d")
    shortcut = voice.segments("![fig1]\n\n[fig1]: http://evil.example/z.png")
    for segs in (own_line, inline, ref_style, shortcut):
        images = [s for s in segs if s["kind"] == "image"]
        assert len(images) == 1
        assert not any("![" in s["text"] for s in segs if s["kind"] == "text")
        assert voice.check_images(images, d, "t02-owner")[0]["ok"] is False
    for segs in (own_line, inline, ref_style):
        assert not any("http" in s["text"] for s in segs if s["kind"] == "text")
    assert [s["kind"] for s in inline] == ["text", "image", "text"]
    assert inline[0]["text"] == "See" and inline[2]["text"] == "mid-sentence."
    assert ref_style[0]["ref"] == "" and ref_style[0]["name"] == "[fig1]"
    assert shortcut[0]["ref"] == "" and shortcut[0]["name"] == "![fig1]"
    # Inside inline code, `![` is text: Markdown draws no image in a code span,
    # and the rules ask for identifiers in backticks.
    code = voice.measure("Use `vec![0]` here, and `rows![0]` too.")
    assert code["images"] == [] and voice.violations(code, "tl") == []
    assert voice.segments("Use `vec![0]` here.") == [{"kind": "text", "text": "Use `vec![0]` here."}]
    # An escaped backtick, or one in a longer run, opens no code span: Markdown
    # draws the image, so it is one.
    for body in ("See \\`![x](http://evil.example/y.png)` here.",
                 "See ``![x](http://evil.example/y.png)` here.",
                 "See `![x](http://evil.example/y.png)`` here."):
        assert [s["kind"] for s in voice.segments(body)] == ["text", "image", "text"], body
    # A "(" with no ")" after it on the line leaves the bare label as the image.
    assert voice.segments("See ![x](oops here.") == [
        {"kind": "text", "text": "See"},
        {"kind": "image", "name": "![x]", "ref": "", "caption": "x", "description": "",
         "ok": None},
        {"kind": "text", "text": "(oops here."},
    ]


def test_captions_and_descriptions_are_consumed_into_their_segment():
    segs = voice.segments(
        "Staffing is the risk.\n\n"
        "![staffing](images/t02-owner.svg)\n"
        "Description: engineers per week.\n\n"
        "Figure: the pipeline\n"
        "```mermaid\ngraph TD; A-->B\n```\n"
        "Description: two stages.\n\n"
        "```python\nx = 1\n```\n"
        "Closing line."
    )
    assert segs == [
        {"kind": "text", "text": "Staffing is the risk."},
        {"kind": "image", "name": "t02-owner.svg", "ref": "images/t02-owner.svg",
         "caption": "staffing", "description": "engineers per week.", "ok": None},
        {"kind": "mermaid", "source": "graph TD; A-->B", "caption": "the pipeline",
         "description": "two stages."},
        {"kind": "text", "text": "```python\nx = 1\n```\nClosing line."},
    ]
    # a Description: line just above the image is its description too
    assert voice.segments("Description: engineers per week.\n![c](images/t02-owner.svg)") == [
        {"kind": "image", "name": "t02-owner.svg", "ref": "images/t02-owner.svg",
         "caption": "c", "description": "engineers per week.", "ok": None},
    ]


def test_uncaptioned_images_and_a_bare_mermaid_fence():
    assert voice.measure("![](images/t02-owner.svg)\nDescription: d")["images_uncaptioned"] == 1
    assert voice.measure("![c](images/t02-owner.svg)")["images_uncaptioned"] == 1
    long = "Description: " + "word " * 41
    assert voice.measure("![c](images/t02-owner.svg)\n" + long)["images_uncaptioned"] == 1
    bare = voice.measure("```mermaid\ngraph TD; A-->B\n```")
    assert bare["images"][0]["kind"] == "mermaid" and bare["images_uncaptioned"] == 1
    assert voice.check_images(bare["images"], "/nonexistent", "t02-owner")[0]["ok"] is True


def test_check_images_never_raises():
    assert voice.check_images([{"kind": "image", "name": None, "ref": None}], None, "") == [
        {"kind": "image", "name": None, "ref": None, "ok": False}]
