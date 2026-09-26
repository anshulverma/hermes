"""The committee's voice rules and the measurement of one turn (voice.py)."""
from __future__ import annotations

import hashlib
import json
import os
import threading
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
    assert m["first_line_words"] == 2  # the first sentence, "Defer it."
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
    assert m["tells"] == {"process": 1, "turn_refs": 1, "unchanged": 1, "hedge": 0,
                          "preempt": 1, "filler": 2}
    assert m["filler_hits"] == 6


@pytest.mark.parametrize("kind_, text, n", [
    ("process", "I've reviewed it. I have cross-checked it. I re-read it. I went through it.", 4),
    ("process", "Having read the doc, and after reviewing it, Let me say I can confirm it.", 4),
    ("process", "I rewrote section 4 and I will own it.", 0),
    ("turn_refs", "As turns 3 and turn 12 said, and t04 too, and T05.", 4),
    ("turn_refs", "Returns 3 rows; the t100 path.", 0),
    ("unchanged", "The original stays intact. The original was left alone. Nothing was modified.", 3),
    ("unchanged", "The original was not touched.", 1),
    ("hedge", "I think it breaks. I believe so. Perhaps it might, and could potentially, "
              "arguably. It seems so.", 7),
    ("hedge", "It breaks when two hosts retry at once.", 0),
])
def test_each_tell_pattern_counts_its_narration(kind_, text, n):
    assert voice.measure(text)["tells"][kind_] == n


def test_two_filler_phrases_force_a_retake_and_one_does_not():
    two = voice.measure("Great question. Defer it: `a.py:1` for example. Hope this helps.")
    assert two["filler_phrases"] == {"great question": 1, "hope this helps": 1}
    assert voice.violations(two, "tl") == ["filler"]
    one = voice.measure("Great question. Defer it: `a.py:1` for example.")
    assert voice.violations(one, "tl") == []


def test_the_hard_filler_list_is_stock_filler_nobody_says_in_a_meeting():
    assert voice.STOCK_FILLER == (
        "great question", "hope this helps", "i hope this helps", "it's worth noting",
        "it is worth noting", "i'd be happy to help", "happy to help", "let's dive in",
        "let's dive into", "as an ai",
    )


# Each of these read as two filler phrases, and was sent back, when filler was
# any FILLER substring anywhere in the prose, quotes included.
_NOT_FILLER = (
    "I'd be happy to pair with Ruth on the migration in section 4.",
    "I want to be clear about the owner: section 3 names none.",
    "The queue has to be cleared by hand, and the runbook that said otherwise is stale.",
    "Ruth is unhappy to own the pager, and section 4 never delved into staffing.",
    "The doc opens with 'To be clear' and closes with 'That said, ship it', section 2.",
)


@pytest.mark.parametrize("text", _NOT_FILLER)
def test_a_sentence_that_only_contains_a_filler_phrase_is_not_sent_back(text):
    m = voice.measure(text)
    assert m["filler_phrases"] == {} and "filler" not in voice.violations(m, "tl")
    assert m["tells"]["filler"] == 2  # eval's C8 count is unchanged


_FILLER_SLOP = (
    "Great question! Defer it: section 3 names no owner for the migration. Hope this helps.",
    "Happy to help here. It's worth noting that the retry loop at `engine/dispatch.py:284` "
    "never backs off.",
    "Let's dive in. The rollout in section 7 has no rollback, for example for a failed canary. "
    "I hope this helps!",
    "As an AI reviewer I would defer: it is worth noting that §6.2 keeps two write paths live.",
    "I’d be happy to help size it. It’s worth noting that section 15 gives no estimate.",
)


@pytest.mark.parametrize("text", _FILLER_SLOP)
def test_stock_filler_slop_is_sent_back(text):
    assert voice.violations(voice.measure(text), "tl") == ["filler"]


def test_overlapping_filler_phrases_count_once_and_quoted_ones_not_at_all():
    assert voice.measure("I'd be happy to help.")["filler_phrases"] == {"i'd be happy to help": 1}
    assert voice.measure("I hope this helps.")["filler_phrases"] == {"i hope this helps": 1}
    assert voice.measure("Let's dive into it.")["filler_phrases"] == {"let's dive into": 1}
    assert voice.violations(voice.measure("I'd be happy to help."), "tl") == []
    # whole words only
    assert voice.measure("A great questionnaire; Ruth is unhappy to help-desk it.")[
        "filler_phrases"] == {}
    quoted = ('The intro reads "Great question" and the close \'Hope this helps\'.\n'
              "> Great question. Hope this helps.\n\n"
              "Defer it: `hope this helps` in `a.py:1`, for example.")
    m = voice.measure(quoted)
    assert m["filler_phrases"] == {} and voice.violations(m, "tl") == []


def test_the_broader_filler_list_is_counted_and_badged_never_sent_back():
    m = voice.measure("To be clear, defer it. That said, `a.py:1` for example. In summary, no.")
    assert m["tells"]["filler"] == 3 and m["filler_phrases"] == {}
    assert voice.violations(m, "tl") == [] and voice.flags(m, "tl") == ["tells"]


def test_the_filler_note_names_the_phrases_found():
    m = voice.measure("Great question. Defer it. Hope this helps. Great question.")
    assert m["filler_phrases"] == {"great question": 2, "hope this helps": 1}
    assert voice.note(m, ["filler"], take=2) == (
        "Retake 2 of 3. Rules broken: 3 filler phrases: 'great question', 'hope this helps'. "
        "Say it again within them.")
    # after an image rule and the word cap, the names still fit the clip whole
    m = voice.measure("It’s worth noting this. I hope this helps. " + "word " * 160)
    full = voice.note(m, ["over_cap", "image_missing", "filler"], take=3, image="t02-owner")
    assert full == (
        "Retake 3 of 3. Rules broken: an image not at images/t02-owner.svg or .png; "
        "168 words (cap 150); 2 filler phrases: 'it's worth noting', 'i hope this helps'. "
        "Say it again within them.")
    from playbooks.committee import cast
    assert cast.clip(full, voice.RETAKE_NOTE_MAX) == full


def test_narration_and_hedging_are_a_soft_tells_flag_never_a_retake():
    for text in ("I checked it. Defer: `a.py:1` for example.",
                 "As turn 3 said, defer: `a.py:1` for example.",
                 "The original is intact. Defer: `a.py:1` for example.",
                 "I think we defer: `a.py:1` for example.",
                 "Great question: defer, `a.py:1` for example."):
        m = voice.measure(text)
        assert voice.flags(m, "tl") == ["tells"], text
        assert voice.violations(m, "tl") == [], text
    # a pre-empting phrase alone is neither: rule 6 is measured, not badged
    assert voice.flags(voice.measure("Defer rather than ship: `a.py:1` for example."), "tl") == []


# What the user asked for (direct replies with code pointers) keeps its first
# take; slop is sent back for filler or flagged for its narration and hedging.
_GOOD = (
    ("tl", "Defer it: the retry loop at `engine/dispatch.py:284` never backs off, so one dead "
           "host pages all night. For example, h3 failed 40 times in 10 min last week. Cap "
           "retries at 5 and add jitter before this ships."),
    ("owner", "Conceded on the cap: I will bound retries at 5 in `engine/dispatch.py:284`. I "
              "disagree on staffing, because section 4 already names Ruth's team for the "
              "migration, and §6.2 keeps the old path live for 2 weeks."),
    ("data_scientist", "The 30% latency win has no baseline. Section 3 compares a warm cache "
                       "against a cold one, so the gain could be the cache alone. Rerun "
                       "`bench/latency.py:40` with both caches warm and report p99 for each."),
    ("tpm", "Approve with one date: the schema change in `db/migrations/0042.sql:1` blocks the "
            "billing team, and nobody owns that handoff. Name an owner and a date for it in "
            "section 5, for example Sam by Oct. 10."),
    ("junior_ic", "Added the rollback section under section 4 naming the on-call rotation as "
                  "the pager owner, per the 'Why now?' note."),
)
_SLOP = (
    ("tl", "Great question. I've reviewed the document carefully, and I think the proposal is "
           "strong overall. It's worth noting that the retry logic might need more thought. "
           "Hope this helps!"),
    ("owner", "Let me address each point. As turn 5 said, the original document remains "
              "unchanged, which is by design. To be clear, I believe we should proceed."),
    ("pm", "Having read the thread, I can confirm the concerns in t04 were addressed. That said, "
           "it seems the rollout could potentially slip. In summary, I'm happy to approve."),
    ("junior_ic", "I checked the file and the original is intact; nothing was modified outside "
                  "the new section."),
    ("staff_ic", "Perhaps the migration plan is arguably fine, but I think the staffing might be "
                 "thin. At the end of the day, let's dive into section 4."),
)


@pytest.mark.parametrize("role, text", _GOOD)
def test_a_direct_reply_with_a_code_pointer_keeps_its_first_take(role, text):
    m = voice.measure(text, role)
    assert voice.violations(m, role) == []
    assert "tells" not in voice.flags(m, role)


@pytest.mark.parametrize("role, text", _SLOP)
def test_slop_is_sent_back_for_filler_or_flagged_for_its_tells(role, text):
    m = voice.measure(text, role)
    hard, soft = voice.violations(m, role), voice.flags(m, role)
    assert "filler" in hard or "tells" in soft
    assert set(hard) <= {"filler"}  # hedging and narration stay soft


def test_bold_counts_prose_not_quotes_blockquotes_or_exponents():
    assert voice.measure('The doc says "the **new** path" is safe.')["bold"] == 0
    assert voice.measure("The doc says 'the **new** path' is safe.")["bold"] == 0
    assert voice.measure("> The **new** path is safe.\n\nDefer it.")["bold"] == 0
    assert voice.measure("That is 2**10 and 3**4 bytes.")["bold"] == 0
    assert voice.measure("That is **10 hosts** now.")["bold"] == 1
    assert voice.measure("A **bold** claim.")["bold"] == 1


def test_sentences_skip_abbreviations_and_quoted_questions():
    for text in ("Ship it by Jan. 5 at approx. 3 pm.", "Ship by Sept. 5 not Sep. 9.",
                 "Waits 3 sec. per host, no. 4 on the list.",
                 "Renamed the 'Why now?' heading.", 'Renamed the "Why now?" heading.'):
        assert voice.measure(text)["sentences"] == 1, text
    for text in ("Added a rollback step (e.g. drain the canary first) to section 7.",
                 "Moved the owner line up (i.e. above the risks) in section 2.",
                 "Added the 9 a.m. freeze window to section 4, and the 5 p.m. one to section 5.",
                 "Replaced the U.S. region list in section 4 with the three regions Ruth named."):
        m = voice.measure(text, "junior_ic")
        assert m["sentences"] == 1 and voice.violations(m, "junior_ic") == [], text
    assert voice.measure("I added the rollback plan")["sentences"] == 1  # V8: no end mark
    assert voice.measure("Owner's call. It's done.")["sentences"] == 2


def test_a_caption_over_15_words_is_uncaptioned():
    fifteen = " ".join(["w"] * 15)
    ok = voice.measure(f"![{fifteen}](images/t02-owner.svg)\nDescription: d")
    assert ok["images_uncaptioned"] == 0
    long = voice.measure(f"![{fifteen} x](images/t02-owner.svg)\nDescription: d")
    assert long["images_uncaptioned"] == 1
    fig = voice.measure(f"Figure: {fifteen} x\n```mermaid\ngraph TD; A-->B\n```\nDescription: d")
    assert fig["images_uncaptioned"] == 1
    # V2: a 40-word description is not uncaptioned
    forty = "Description: " + " ".join(["w"] * 40)
    assert voice.measure("![c](images/t02-owner.svg)\n" + forty)["images_uncaptioned"] == 0


def test_long_first_line_measures_the_first_sentence():
    m = voice.measure("Defer it: section 3 names no owner. " + "word " * 30 + ".")
    assert m["first_line_words"] == 7
    assert "long_first_line" not in voice.flags(m, "tl")
    assert voice.measure("word " * 30)["first_line_words"] == 30


def test_a_fence_is_indented_by_spaces_only_and_a_backtick_fence_has_no_backtick_info():
    wall = "# Title\n**bold** " + "word " * 400
    # a tab or a no-break space indents no fence, at the opener or at the closer
    for body in (f"\t```\n{wall}\n\t```", f"\t```\n{wall}\n```", f"```\n{wall}\n\t```",
                 f"\u00a0```\n{wall}\n\u00a0```", f"``` x`y\n{wall}\n```"):
        m = voice.measure(body)
        assert m["words"] > 400 and m["headers"] == 1 and m["bold"] == 1, body[:8]
        assert voice.violations(m, "tl")[:1] == ["over_cap"]
    tilde = voice.measure("~~~ x`y\n# x\n~~~")
    assert (tilde["fenced_lines"], tilde["headers"]) == (1, 0)
    assert voice.measure("   ```\n# x\n   ```  ")["fenced_lines"] == 1


def test_a_tab_indented_fence_inside_a_list_item_is_a_fence():
    # A tab reaches the content of an item whose text starts by column 4, so
    # Markdown renders this as code inside item 1, not a heading.
    body = ("Defer it: the retry loop at `engine/dispatch.py:284` never backs off, for example:\n"
            "1. Add a backoff:\n\t```python\n\t# cap the retries\n\tfor i in range(3):\n"
            "\t    retry(**opts)\n\t```\n")
    m = voice.measure(body, "tl")
    assert (m["headers"], m["bold"], m["fenced_lines"]) == (0, 0, 3)
    assert m["words"] == 16 and voice.violations(m, "tl") == []
    # under an item's indented continuation, across a blank line, too
    assert voice.measure("- a\n  more\n\n\t```\n\t# x\n\t```")["fenced_lines"] == 1
    assert voice.measure("  - x\n\t```\n\ty\n\t```")["fenced_lines"] == 1
    # an item whose text starts past column 4 is out of a tab's reach, and a
    # flush-left line ends the item and the fence with it: both stay prose
    for body in ("100. x\n\t```\n\tone two\n\t```", "   - x\n\t```\n\tone two\n\t```"):
        assert voice.measure(body)["fenced_lines"] == 0, body
    assert voice.measure("- x\n\t```\n# Title\n\t```")["headers"] == 1
    # a tab-indented fence closes only on a tab-indented closer, and one on
    # the body's first line is under nothing (never read against the last line)
    assert voice.measure("- x\n\t```\n# Title\n```")["headers"] == 1
    assert voice.measure("\t```\n- a\n\t```")["bullets"] == 1
    # a tab-indented # is never a heading: at the top level it is code or text
    assert voice.measure("Defer it.\n\t# not a heading")["headers"] == 0


def test_a_setext_underline_after_a_prose_line_is_a_header():
    assert voice.measure("Title\n=====\nDefer it.")["headers"] == 1
    assert voice.measure("Title\n---\nDefer it.")["headers"] == 1
    assert voice.measure("Defer it.\n\n---\n\nMore.")["headers"] == 0  # a break, not a heading
    assert voice.measure("- one\n---")["headers"] == 0
    # Under a blockquote line it is a thematic break, under an item's indented
    # continuation an empty item or a break (micromark): no heading either way.
    assert voice.measure("Defer it: section 3 says\n> the owner is TBD\n---\nName one.")[
        "headers"] == 0
    assert voice.measure("Defer it, for example:\n- first point\n  continues here\n-\nDone.")[
        "headers"] == 0
    assert voice.measure("- first point\n\n  continues here\n---\nDone.")["headers"] == 0
    # once a flush-left line after a blank line has left the list, it is a heading again
    assert voice.measure("- first point\n\nTitle\n---\nDefer it.")["headers"] == 1


def test_measure_keeps_eight_image_records_and_counts_them_all():
    body = "\n".join(f"![c{n}](images/t02-owner.svg)" for n in range(20))
    m = voice.measure(body)
    assert len(m["images"]) == 8 and m["images_count"] == 20
    assert "too_many_images" in voice.violations(m, "tl")
    assert voice.note(m, ["too_many_images"], take=2).startswith(
        "Retake 2 of 3. Rules broken: 20 images (max 1)")


def test_segments_stop_making_figures_at_the_limit():
    body = "Lead.\n" + "\n".join(f"![c{n}](images/x{n}.svg)" for n in range(12)) + "\nTail."
    segs = voice.segments(body, limit=8)
    figures = [s for s in segs if s["kind"] != "text"]
    assert len(figures) == 8 and [s["caption"] for s in figures] == [f"c{n}" for n in range(8)]
    assert segs[-1] == {"kind": "text", "text": "![c8](images/x8.svg)\n![c9](images/x9.svg)\n"
                                                "![c10](images/x10.svg)\n![c11](images/x11.svg)\nTail."}
    assert voice.segments(body) == voice.segments(body, limit=None)
    assert len([s for s in voice.segments(body) if s["kind"] == "image"]) == 12


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


# ~200 KB each, aimed at every pattern the tells, bold, sentence, setext and
# fence rules added: openers that never close, prefixes that never finish.
_CRAFTED = (
    "I have " * 30_000, "Having " * 30_000, "Let " * 50_000, "I can " * 35_000,
    "turns " * 35_000, "t1" * 100_000, "original " * 25_000,
    "original" + "a" * 200_000, "nothing was " * 20_000, "I thin" * 35_000,
    "could " * 35_000, "'a" * 100_000, " '" + "a" * 200_000, "2**" * 70_000,
    "**a" * 70_000, "> **" * 50_000, "=" * 200_000 + "x", "x\n" + "-" * 200_000 + " x",
    "x\n=\n" * 50_000, "`" * 200_000 + "x`", "```" + "a" * 200_000 + "`",
    "~~~" + "`" * 200_000, "Jan. " * 40_000, "![c](images/x.svg)\n" * 10_000,
    # the stock filler scan: prefixes of the longest phrases, curly apostrophes
    "great question " * 14_000, "i'd be happy to " * 12_500, "i hope this help" * 12_500,
    "it’s worth notin" * 12_500, "’" * 200_000, "as an " * 35_000,
    # the list items a tab-indented fence and a setext underline look back on
    "- x\n\t```\n" * 25_000, "- x\n  y\n-\n" * 20_000, "> x\n---\n" * 25_000,
)


def test_measure_never_raises():
    for junk in (None, "", "```", "![", "![x](", "\x00", 5):
        voice.measure(junk)  # type: ignore[arg-type]
    # measure runs master-side on every take, so a stuck or crafted body must not
    # go quadratic: each of these took seconds to minutes when a pattern rescanned
    # the line from every opener.
    shrinking_openers = "\n".join("`" * n for n in range(1000, 2, -1)) + "\n" + "a\n" * 50_000
    # U+1D1D shares its low byte with the closing curly quote, so str.find
    # cannot skip ahead: a scan from every unclosed opener would show here.
    unclosed_curly = "\u201c\u1d1d" * 100_000
    for body in ("![" * 30_000, "![a](" * 12_000, " __" + "a " * 30_000, "```x\n" * 12_000,
                 "“a" * 30_000, "![c](images/x.svg)\nDescription: a" + " " * 60_000 + "b",
                 " " * 60_000 + "x", "\t" * 60_000 + "x", shrinking_openers, unclosed_curly,
                 *_CRAFTED):
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
    ("owner", {"images": [{"kind": "mermaid", "ok": True}] * 2}, "too_many_images"),
    ("tl", {"images_count": 2}, "too_many_images"),
    ("junior_ic", {"images": [{"kind": "mermaid", "ok": True}]}, "too_many_images"),
    ("chair", {"images": [{"kind": "mermaid", "ok": True}]}, "too_many_images"),
    ("tl", {"images_uncaptioned": 1}, "image_uncaptioned"),
    ("tl", {"images": [{"kind": "image", "ok": False}]}, "image_missing"),
    ("owner", {"action_chars": turnblock.ACTION_MAX + 1}, "action_too_long"),
    ("owner", {"stance_chars": turnblock.STANCE_MAX + 1}, "stance_too_long"),
    ("tl", {"stance_chars": turnblock.STANCE_MAX + 1}, "stance_too_long"),
    ("tl", {"filler_phrases": {"great question": 2}}, "filler"),
    ("chair", {"filler_phrases": {"great question": 1, "hope this helps": 2}}, "filler"),
])
def test_each_hard_rule_is_its_own_violation(role, over, slug):
    assert voice.violations(_m(**over), role) == [slug]


def test_a_compliant_turn_breaks_nothing_and_the_limits_are_inclusive():
    assert voice.violations(_m(words=150, bullets=5), "tl") == []
    assert voice.violations(_m(words=300, bullets=8), "chair") == []
    assert voice.violations(_m(action_chars=turnblock.ACTION_MAX), "owner") == []
    assert voice.violations(_m(action_chars=999), "tl") == []  # owner only
    assert voice.violations(_m(stance_chars=turnblock.STANCE_MAX), "owner") == []
    # only the owner and the reviewers are asked for a stance
    assert voice.violations(_m(stance_chars=999), "chair") == []
    assert voice.violations(_m(stance_chars=999), "junior_ic") == []
    assert voice.violations(_m(filler_phrases={"great question": 1}), "tl") == []
    # the broader FILLER count is eval's and the tells badge's, never a retake
    assert voice.violations(_m(tells={"filler": 5}), "tl") == []
    assert voice.violations(_m(tells=["junk"], images_count="x", filler_phrases="x"), "tl") == []
    assert voice.violations(_m(filler_phrases={"a": "x", "b": True, "c": None}), "tl") == []


def test_a_two_sentence_one_line_junior_report_is_multi_sentence():
    m = voice.measure("I added the rollback plan. It is in section 4.", "junior_ic")
    assert voice.violations(m, "junior_ic") == ["multi_sentence"]
    # everyone else may say two sentences
    two = voice.measure("Defer it. Section 3 names no owner.")
    for role in ("tl", "owner", "chair"):
        assert voice.violations(two, role) == [], role
    # V7: a junior report of exactly 40 words is compliant
    forty = voice.measure(" ".join(["w"] * 39) + " done.", "junior_ic")
    assert forty["words"] == 40 and voice.violations(forty, "junior_ic") == []


def test_flags_are_soft_and_role_scoped():
    m = voice.measure("Defer it — " + "word " * 30)
    assert voice.flags(m, "tl") == ["no_pointer", "no_example", "dashes", "long_first_line"]
    assert voice.flags(m, "junior_ic") == ["dashes", "long_first_line"]
    assert voice.flags(_m(stance_chars=201), "chair") == ["stance_clipped"]
    assert voice.violations(m, "tl") == []


def test_a_path_line_inside_a_fence_is_a_pointer():
    # V9, spec C2: pointers_path_line runs over the whole body, fences included
    m = voice.measure("Defer it.\n\n```\nengine/dispatch.py:284\n```")
    assert (m["pointers_path_line"], m["pointers"]) == (1, 1)


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
    # One blank line ends the numbered list, so Markdown never folds the
    # unnumbered additions into rule 13.
    assert voice.RULES.count("") == 1
    assert voice.RULES[voice.RULES.index("") - 1].startswith("13. ")
    # Rules 8 and 9 ask for a pointer and an example; they never discourage one.
    assert "path:line" in voice.RULES[7] and "example" in voice.RULES[7]
    assert "`" in voice.RULES[8]
    # Filler and hedging are named with examples, and one good turn is shown whole.
    filler = next(line for line in voice.RULES if "filler" in line.lower())
    assert "'Great question" in filler and "I think" in filler
    good = next(line for line in voice.RULES if line.startswith("A good turn"))
    shown = voice.measure(good.split(": ", 1)[1].strip("'"))
    assert shown["pointers_path_line"] == 1 and shown["examples"] > 0
    assert voice.violations(shown, "tl") == [] and voice.flags(shown, "tl") == []
    images = next(line for line in voice.RULES if line.startswith("Images:"))
    assert "15 words or fewer" in images and "40 words or fewer" in images


def test_note_phrases_each_slug_image_rules_first():
    m = _m(words=212, bold=3, cap=150)
    assert voice.note(m, ["over_cap", "bold"], take=2) == (
        "Retake 2 of 3. Rules broken: 212 words (cap 150); 3 bold. Say it again within them."
    )
    # Both image rules, the word cap and one more count fit the clip whole,
    # the expected file named and the instruction last; the image rules lead,
    # so a longer list loses a count the speaker can see by rereading, never an
    # image check made master-side.
    m = _m(words=212, headers=2, bold=3, nested_bullets=2, cap=150)
    four = voice.note(m, ["over_cap", "headers", "image_uncaptioned", "image_missing"],
                      take=3, image="t02-owner")
    assert four == (
        "Retake 3 of 3. Rules broken: a caption over 15 words, a description over 40, or "
        "either missing; an image not at images/t02-owner.svg or .png; 212 words (cap 150); "
        "2 headers. Say it again within them."
    )
    from playbooks.committee import cast
    assert cast.clip(four, voice.RETAKE_NOTE_MAX) == four
    six = cast.clip(voice.note(m, ["over_cap", "headers", "bold", "nested", "image_uncaptioned",
                                   "image_missing"], take=3, image="t02-owner"),
                    voice.RETAKE_NOTE_MAX)
    assert six.startswith(four.removesuffix(". Say it again within them.")) and six.endswith("…")
    # a speaker offered no image is never told a file name
    assert "an image missing or not your own file" in voice.note(m, ["image_missing"], take=2)
    every = _m(words=400, lines=3, sentences=4, headers=1, bold=2, tables=1,
               nested_bullets=2, bullets=9, images=[{}, {}], action_chars=250, kind="chair",
               stance_chars=260, filler_phrases={"great question": 2, "hope this helps": 1})
    said = voice.note(every, [
        "over_cap", "multi_line", "multi_sentence", "headers", "bold", "tables", "nested",
        "too_many_bullets", "too_many_images", "image_uncaptioned", "image_missing",
        "action_too_long", "stance_too_long", "filler"], take=3)
    for phrase in ("400 words (cap", "3 lines (one allowed)", "4 sentences (one allowed)",
                   "1 headers", "2 bold", "1 tables", "2 nested bullets", "9 bullets (max 8)",
                   "2 images (max 0)",
                   "a caption over 15 words, a description over 40, or either missing",
                   "an image missing or not your own file",
                   "action 250 characters (max 200)", "stance 260 characters (max 200)",
                   "3 filler phrases: 'great question', 'hope this helps'"):
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


def test_summary_boundaries_are_inclusive_and_nesting_is_unclean():
    rows = [
        ("turn", {"role": "tl", "voice": _v(150)}),  # V13: words == cap is within cap
        ("turn", {"role": "owner", "voice": _v(20, nested_bullets=1)}),  # V15
        ("turn", {"role": "junior_ic", "voice": _v(40, cap=40)}),  # V7: 40 words compliant
    ]
    s = voice.summary(rows)
    assert s["owner_reviewer_pct_within_cap"] == 100.0
    assert s["pct_clean_format"] == 66.7
    assert s["junior_pct_compliant"] == 100.0


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
    # the sha256 of the exact bytes checked, so the view can pin what it serves
    assert svg[0]["sha256"] == hashlib.sha256(b"\xef\xbb\xbf  " + SVG).hexdigest()
    assert png[0]["sha256"] == hashlib.sha256(PNG).hexdigest()
    (d / "t02-owner.svg").write_bytes(b'<?xml version="1.0"?>\n' + SVG)
    prolog = voice.check_images(_img("![c](images/t02-owner.svg)\nDescription: d"), d, "t02-owner")
    assert prolog[0]["ok"] is True


def test_an_image_of_exactly_the_cap_is_ok(tmp_path):
    d = _dir(tmp_path)
    (d / "t02-owner.svg").write_bytes(SVG + b" " * (voice.IMAGE_MAX_BYTES - len(SVG)))
    images = voice.check_images(_img("![c](images/t02-owner.svg)\nDescription: d"), d, "t02-owner")
    assert images[0]["ok"] is True and len(images[0]["sha256"]) == 64


def test_only_a_passing_file_image_carries_a_sha256(tmp_path):
    d = _dir(tmp_path)
    body = "Figure: f\n```mermaid\ngraph TD; A-->B\n```\nDescription: d\n\n![c](images/t02-owner.svg)"
    stale = [{**im, "sha256": "0" * 64} for im in _img(body)]
    images = voice.check_images(stale, d, "t02-owner")
    assert [im["ok"] for im in images] == [True, False]
    assert all("sha256" not in im for im in images)


@pytest.mark.parametrize("prepare", ["missing", "symlink", "oversize", "badmagic", "foreign",
                                     "pngmagic", "fifo"])
def test_a_bad_file_image_is_not_ok(tmp_path, prepare):
    d = _dir(tmp_path)
    target = d / "t02-owner.svg"
    name = "t02-owner.svg"
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
        name = "t04-tl.svg"
    elif prepare == "pngmagic":  # a .png must carry the PNG magic
        (d / "t02-owner.png").write_bytes(b"GIF89a" + b"\x00" * 16)
        name = "t02-owner.png"
    elif prepare == "fifo":  # opening a FIFO must neither hang nor pass
        os.mkfifo(target)
    images = []
    worker = threading.Thread(target=lambda: images.extend(voice.check_images(
        _img(f"![c](images/{name})\nDescription: d"), d, "t02-owner")), daemon=True)
    worker.start()
    worker.join(2)
    assert not worker.is_alive(), "check_images hung"
    assert images[0]["ok"] is False and "sha256" not in images[0]
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
