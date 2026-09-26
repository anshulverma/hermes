"""The committee's voice: the rules every speaker follows, and one measure of a turn.

This is the interim single source of the voice rules (committee-eval D11). The
eval's concision score reads ``measure``, and its concision version hashes
``RULES``, so a rules change moves that version and old scores stop comparing
instead of comparing silently. committee-voice rewrites this file in place,
keeping both names and a superset of ``measure``'s keys.

``RULES`` was distilled once, in the playbook's own words, from the
diff-authoring skill. Nothing reads that skill at runtime.

Stdlib-only.
"""
from __future__ import annotations

import re

RULES: tuple[str, ...] = (
    "Lead with the point: your verdict or your ask goes first, the reasons after it.",
    "Keep each bullet to about a line and a half; split or cut anything longer.",
    "No walls of text: break a long paragraph up, or turn it into a short list.",
    "Do not defend your choices in advance; state them, and answer an objection when someone raises it.",
    "Be concrete: give an example, a number, or a pointer such as eval.py:12 or section 3.2.",
)

# C8's phrases, in C8's order; each is counted as a case-insensitive substring.
FILLER: tuple[str, ...] = (
    "great question", "it's worth noting", "it is worth noting", "to be clear",
    "let me be clear", "i want to be clear", "at the end of the day", "that said",
    "happy to", "i'd be happy", "in summary", "to summarize", "hope this helps",
    "let's dive", "delve",
)

# The lookbehind starts a match only at a token's first char, so one long token stays linear.
_PATH_LINE = re.compile(r"(?<![\w./-])[\w./-]+\.\w+:\d+(-\d+)?")
_SECTION = re.compile(r"§\s?\d+(\.\d+)*|\b[Ss]ection \d+(\.\d+)*")
_EXAMPLE_PHRASES = ("for example", "e.g.", "for instance", "such as")
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_UNIT = re.compile(r"\b\d+(\.\d+)?\s?(ms|s|min|h|%|KB|MB|GB|x|QPS)\b")


def _count(pattern: re.Pattern, text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def measure(body: str, role: str = "reviewer") -> dict:
    """Count one turn's words, pointers, examples, longest paragraph and filler (C8).

    Pure, and never raises: a non-str body counts as "". ``role`` is unused
    until committee-voice gives each role its own cap.
    """
    text = body if isinstance(body, str) else ""
    longest = run = fences = 0
    inside = False
    outside: list[str] = []  # the lines outside fenced blocks, fence lines excluded
    for line in text.splitlines():
        if line.strip():  # a paragraph is a maximal run of non-blank lines
            run += len(line.split())
            longest = max(longest, run)
        else:
            run = 0
        if line.lstrip().startswith("```"):
            fences += 1
            inside = not inside
        elif not inside:
            outside.append(line)
    low = text.lower()
    examples = (
        sum(low.count(p) for p in _EXAMPLE_PHRASES)
        + _count(_INLINE_CODE, "\n".join(outside))
        + fences // 2
        + _count(_UNIT, text)
    )
    return {
        "words": len(text.split()),
        "pointers": _count(_PATH_LINE, text) + _count(_SECTION, text),
        "examples": examples,
        "longest_paragraph_words": longest,
        "filler_hits": sum(low.count(p) for p in FILLER),
    }
