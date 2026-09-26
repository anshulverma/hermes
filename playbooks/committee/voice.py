"""How a committee member talks: the ground rules, and the measurement of one turn.

The single source for the rules text the thread header carries, the per-role
caps, the metrics a turn is measured by, the hard violations that send a speaker
back for another take, the soft flags that never do, the image grammar and the
run summary. The eval, the view and later loops read these names; none restates
a rule.

``measure`` runs on the speaker's own prose (``turnblock.strip(answer)``), never
on thread.md or the assembled verdict. Fenced blocks, image references and the
lines that caption an image are not prose: they add no words and break no
formatting rule. ``check_images`` is the only function here that touches the
filesystem.

Stdlib-only. Imports turnblock for the action and stance caps, never cast.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import statistics
from collections.abc import Iterable

from playbooks.committee import turnblock

RULES_VERSION = "voice-1"
MAX_TAKES = 3
RETAKE_NOTE_MAX = 200
CAPS = {"reviewer": 150, "owner": 150, "junior_ic": 40, "chair": 300}
MAX_BULLETS = {"chair": 8}  # others 5
IMAGE_MAX_BYTES = 2 * 1024 * 1024

_BULLETS = 5
_IMAGES = {"owner": 1, "reviewer": 1, "junior_ic": 0, "chair": 0}
_CAPTION_WORDS = 15
_DESCRIPTION_WORDS = 40
_FIRST_LINE_WORDS = 25
_FILLER_MAX = 1  # two filler phrases send a take back; one is only counted
# The image records measure keeps (it counts them all, in images_count), and
# the figures segments(limit=...) draws: one oversized answer must not store or
# render thousands of them.
IMAGE_RECORDS = 8

# One line each: the header renders "\n".join(RULES). No element starts with
# "#", none carries bold or a long or short dash, so no rules line can read as
# a heading, a roster line or a violation of the rules it states. The one blank
# element ends the numbered list, so Markdown never folds the unnumbered
# additions into rule 13.
RULES: tuple[str, ...] = (
    "1. Lead with your position, then the reason. Bad: 'Thanks, a few thoughts on section 3.' Good: 'Defer it: section 3 names no owner for the migration.'",
    "2. Stay under your cap: owner and reviewers 150 words, the chair 300, the junior IC one sentence of 40 words or fewer. Over it, you are asked to say it again.",
    "3. Plain prose plus at most 5 one-line bullets (the chair 8). Never a paragraph inside a bullet.",
    "4. Do not over-structure: no headers, no bold, no tables, no nested bullets.",
    "5. No dashes as punctuation, long or short. Use a colon, a comma or two sentences.",
    "6. Do not answer objections nobody raised. Tells: 'rather than', 'instead of', 'would have', 'does not mean', 'what this buys'.",
    "7. Cut any sentence that would be true of every proposal. Bad: 'Getting this right matters.'",
    "8. Say what a change does and why it matters, then point at the code with a path:line and give one example; skip how each piece works.",
    "9. Name the category, then one instance the room can check: 'the retry paths, such as `engine/dispatch.py:284`', never a list of identifiers nobody has seen.",
    "10. No meta-talk about the meeting, your process or your answer.",
    "11. No unexplained labels: say in plain words what a code or an acronym means.",
    "12. Give the pointer, not the proof: a section of the artifact, or a repo path:line such as `engine/dispatch.py:284`. A count names how it was counted.",
    "13. Reread before you send: count your bullets, look for dashes and bold.",
    "",
    "No filler and no hedging: never 'Great question', 'Hope this helps', 'It's worth noting' or 'To be clear'. Bad: 'I think this might perhaps break.' Good: 'This breaks when two hosts retry at once.'",
    "A good turn, whole: 'Defer it: the retry loop at `engine/dispatch.py:284` never backs off, so one dead host pages all night. For example, h3 failed 40 times in 10 min.'",
    "Address people by name, never by turn number. Bad: 'As turn 5 said.' Good: 'As Ruth said.'",
    "Do not narrate tools or plumbing: files you read or wrote, the original being unchanged, the guardrails.",
    "Back each objection with one concrete example: a scenario, a number or a snippet.",
    "Put paths, identifiers and commands in backticks.",
    "The chair may add one list of conditions, each with an owner and a date.",
    "Images: the owner and each reviewer may add one, the junior IC and the chair none. Write a line ![caption](images/<your file>), or a line 'Figure: caption' then a mermaid code block, with a caption of 15 words or fewer; then a line 'Description: what it shows' in 40 words or fewer.",
)

# Eval's list, verbatim (eval C8).
FILLER = (
    "great question", "it's worth noting", "it is worth noting", "to be clear",
    "let me be clear", "i want to be clear", "at the end of the day", "that said",
    "happy to", "i'd be happy", "in summary", "to summarize", "hope this helps",
    "let's dive", "delve",
)
_PREEMPT = ("rather than", "instead of", "would have", "does not mean", "what this buys")
_EXAMPLE_PHRASES = ("for example", "e.g.", "for instance", "such as")
_ABBREVIATIONS = frozenset({
    "e.g.", "i.e.", "vs.", "etc.", "cf.", "sec.", "approx.", "no.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.", "sep.", "sept.", "oct.",
    "nov.", "dec.",
})

# CommonMark's fences: indented by up to three SPACES (a tab or a no-break
# space makes an indented code block or a paragraph, not a fence), and a
# backtick fence's info string holds no backtick. Anything else is prose here
# because Markdown renders it as prose.
_FENCE = re.compile(r"^ {0,3}(?:(`{3,})([^`]*)|(~{3,})(.*))$")
_CLOSER = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
# C3's grammar. The reference-style alternative is optional so CommonMark's
# shortcut form `![label]` is split out too: Markdown would otherwise resolve
# it against a `[label]: <url>` line and fetch that url.
_IMAGE = re.compile(r"!\[([^\]\n]*)\](\(([^)\n]*)\)|\[[^\]\n]*\])?")
_IMAGE_LABEL = re.compile(r"!\[[^\]\n]*\]")
# measure runs master-side on every take, so no pattern here may rescan a long
# line from each of many starts. The caption lines are stripped in Python (a
# lazy group before \s*$ is quadratic in inner spaces); quoted spans are found
# by a scanner (``_unquoted``); the __bold__ body is one run to the next "_",
# crossing at most the one newline the original \s could match.
_FIGURE = re.compile(r"^\s*Figure:(.*)$")
_DESCRIPTION = re.compile(r"^\s*Description:(.*)$")
_INLINE_CODE = re.compile(r"`[^`\n]+`")
# What ``_images_in`` masks: a one-backtick code span whose backticks are
# neither escaped nor part of a longer run. Anything else Markdown may draw as
# an image, so it is measured as one.
_CODE_SPAN = re.compile(r"(?<![`\\])`[^`\n]+`(?!`)")
_QUOTE_OPEN = re.compile(r'["“]')
# A single-quoted span, for the sentence and bold counts only: it opens at a
# quote no word char precedes and closes at the next quote no word char
# follows, so the apostrophes in "owner's" and "don't" open nothing. Each scan
# ends at the next quote char, so the whole pass is linear.
_SINGLE = re.compile(r"(?<!\w)['‘][^'‘’\n]+['’](?!\w)")
# A "**" with a digit on both sides is an exponent (2**10), never a delimiter.
_STARS = r"(?:(?<!\d)\*\*|\*\*(?!\d))"
_BOLD = re.compile(
    _STARS + r"(?!\s)[^*\n]+?(?<!\s)" + _STARS
    + r"|(?<![\w/.])__(?![\s_])(?:[^_\n]*\n[^_\n]*|(?=[^_\s]*[^\S\n])[^_\n]*)(?<![\s_])__(?![\w.])"
)
_BLOCKQUOTE = re.compile(r"^ {0,3}>")
_HEADER = re.compile(r"^\s{0,3}#{1,6}\s")
# A setext underline: a line of "=" or "-" alone, right under a prose line,
# makes that line an h1 or h2 in Markdown (fullmatch a line).
_SETEXT = re.compile(r" {0,3}(?:=+|-+)[ \t]*")
_TABLE = re.compile(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?")  # fullmatch a stripped line
_BULLET = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
_NESTED = re.compile(r"^( {2,}|\t)")
_PATH_LINE = re.compile(r"(?<![\w./-])[\w./-]+\.\w+:\d+(-\d+)?")  # lookbehind: linear on one long token
_SECTION = re.compile(r"§\s?\d+(\.\d+)*|\b[Ss]ection \d+(\.\d+)*")
_UNIT = re.compile(r"\b\d+(\.\d+)?(\s?(ms|s|min|h|KB|MB|GB|x|QPS)\b|\s?%)")
# Narration, turn numbers, the unchanged original and hedging: counted and
# flagged (``tells``), never a retake. Each alternative is anchored on a fixed
# word and bounded, so none rescans a long line.
_TELLS = {
    "process": re.compile(
        r"\bI(?:'ve|’ve| have)? (?:checked|verified|re-?read|read|ran|grepped|looked|reviewed"
        r"|went through|cross-checked)\b"
        r"|\b(?:[Hh]aving|[Aa]fter) (?:read|reviewed|reviewing|checked)\b|\bLet me\b"
        r"|\bI can confirm\b"
    ),
    "turn_refs": re.compile(r"(?i)\bturns? \d{1,3}\b|\bt\d{2}\b"),
    "unchanged": re.compile(
        r"(?i)original[^.\n]{0,40}\b(?:unchanged|untouched|not modified|intact|left alone"
        r"|not touched)|\bnothing was modified\b"
    ),
    "hedge": re.compile(
        r"(?i)\b(?:I think|I believe|perhaps|might|could potentially|arguably|it seems)\b"
    ),
}
# The tells a reader is shown on the turn (``tells`` flag); filler is its own
# hard rule and preempt is rule 6, measured but not badged.
_SOFT_TELLS = ("process", "turn_refs", "unchanged", "hedge")
_PNG = b"\x89PNG\r\n\x1a\n"


# --- roles ----------------------------------------------------------------

def kind(role: str) -> str:
    """owner, junior_ic or chair; every other seat, generated ones included, is a reviewer."""
    return role if role in ("owner", "junior_ic", "chair") else "reviewer"


def cap_for(role: str) -> int:
    return CAPS[kind(role)]


def cap_text(role: str) -> str:
    """The cap as a goal states it."""
    if kind(role) == "junior_ic":
        return "one sentence of 40 words or fewer"
    return f"{cap_for(role)} words"


# --- the image grammar -----------------------------------------------------

def _fences(lines: list[str]) -> list[tuple[int, int, str]]:
    """(open, close, info) for every CLOSED fence. An unclosed fence is prose.

    A fence closes on the next line of its own marker char, at least as long,
    and nothing else. ``longest[ch][k]`` is the longest such line at or below
    line k, so an opener with no closer is skipped without a scan and every
    scan ends on a closer: each line is looked at a bounded number of times.
    """
    closers = [(c.group(1)[0], len(c.group(1))) if (c := _CLOSER.match(line)) else ("", 0)
               for line in lines]
    longest = {ch: [0] * (len(lines) + 1) for ch in "`~"}
    for k in range(len(lines) - 1, -1, -1):
        for ch, below in longest.items():
            below[k] = max(below[k + 1], closers[k][1] if closers[k][0] == ch else 0)
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        marker, info = (m.group(1), m.group(2)) if m and m.group(1) else (
            (m.group(3), m.group(4)) if m else ("", ""))
        ch, size = (marker[0], len(marker)) if m else ("", 0)
        if m and longest[ch][i + 1] >= size:
            j = next(j for j in range(i + 1, len(lines))
                     if closers[j][0] == ch and closers[j][1] >= size)
            out.append((i, j, info.strip().lower()))
            i = j
        i += 1
    return out


def _cut(lines: list[str], fences: list[tuple[int, int, str]], limit: int) -> int | None:
    """The line that holds figure ``limit + 1``, or None when there are no more.

    A figure is a mermaid fence or an image reference outside a fence, in the
    order ``_parse`` emits them. The cut line is never inside a fence.
    """
    starts = {s: info for s, _e, info in fences}
    fenced = {k for s, e, _info in fences for k in range(s, e + 1)}
    seen = 0
    for i, line in enumerate(lines):
        if i in starts:
            seen += starts[i].split()[:1] == ["mermaid"]
        elif i not in fenced:
            seen += len(_images_in(line))
        if seen > limit:
            return i
    return None


def _image(m: re.Match, description: str) -> dict:
    """One image reference. ``ref`` is the raw parenthesised target, "" otherwise."""
    target = m.group(3)
    if target is None:  # reference-style ![caption][label], or the shortcut ![label]
        ref, name = "", m.group(2) or m.group(0)
    else:
        ref = target.strip()
        name = ref[len("images/"):] if ref.startswith("images/") else ref
    return {"kind": "image", "name": name, "ref": ref, "caption": m.group(1).strip(),
            "description": description, "ok": None}


def _images_in(line: str) -> list[re.Match]:
    """The image references on one line, outside a code span (``_CODE_SPAN``).

    Markdown draws no image inside a code span, and the rules ask for
    identifiers in backticks, so `vec![0]` there is text, not an image.
    Masking keeps every offset, so each match indexes the original line.

    The same matches as ``_IMAGE.finditer``, in linear time: finditer would
    rescan to the line's end from every ``![`` with no ``]`` after it, and
    from every ``](`` with no ``)`` after it.
    """
    masked = _CODE_SPAN.sub(lambda m: " " * len(m.group()), line)
    last_bracket, last_paren = masked.rfind("]"), masked.rfind(")")
    out, pos = [], 0
    while (start := masked.find("![", pos)) != -1 and start < last_bracket:
        label_end = _IMAGE_LABEL.match(masked, start).end()
        unclosable = masked.startswith("(", label_end) and label_end > last_paren
        m = _IMAGE.match(masked, start, label_end if unclosable else len(masked))
        out.append(m)
        pos = m.end()
    return out


def _parse(body: str, limit: int | None = None) -> tuple[list[dict], str, int, int]:
    """(segments, prose, closed fences, fenced lines) for one body.

    One walk serves the view and the measurement, so what the room reads as an
    image is exactly what the metrics leave out of the prose. A caption line
    (``Figure:``) and a ``Description:`` line belong to the image beside them:
    they are consumed into its segment and appear in no text segment.

    ``limit`` (the view's) stops the figures there: from the line holding the
    next one, the rest of the body is one raw text segment. The prose and the
    counts are then of the lines before it, so measure never passes one.
    """
    lines = body.splitlines()
    fences = _fences(lines)
    cut = _cut(lines, fences, limit) if limit is not None else None
    if cut is not None:
        segments, *rest = _parse("\n".join(lines[:cut]))
        tail = "\n".join(lines[cut:]).strip()
        return (segments + [{"kind": "text", "text": tail}], *rest)
    fenced: dict[int, tuple[int, int, str]] = {}
    for fence in fences:
        for k in range(fence[0], fence[1] + 1):
            fenced[k] = fence
    consumed: set[int] = set()

    def adjacent(i: int, step: int, pattern: re.Pattern) -> tuple[int | None, str]:
        j = i + step
        while 0 <= j < len(lines):
            if lines[j].strip():
                if j in consumed or j in fenced:
                    return None, ""
                m = pattern.match(lines[j])
                return (j, m.group(1).strip()) if m else (None, "")
            j += step
        return None, ""

    mermaid: dict[int, dict] = {}
    for start, end, info in fences:
        if info.split()[:1] == ["mermaid"]:
            j, caption = adjacent(start, -1, _FIGURE)
            k, description = adjacent(end, 1, _DESCRIPTION)
            consumed.update(x for x in (j, k) if x is not None)
            mermaid[start] = {"kind": "mermaid", "source": "\n".join(lines[start + 1:end]),
                              "caption": caption, "description": description}

    described: dict[int, str] = {}
    for i, line in enumerate(lines):
        if i in fenced or i in consumed or not _images_in(line):
            continue
        j, description = adjacent(i, 1, _DESCRIPTION)
        if j is None:
            j, description = adjacent(i, -1, _DESCRIPTION)
        if j is not None:
            consumed.add(j)
        described[i] = description

    segments: list[dict] = []
    prose: list[str] = []
    text: list[str] = []

    def flush() -> None:
        chunk = "\n".join(text).strip()
        if chunk:
            segments.append({"kind": "text", "text": chunk})
        text.clear()

    i = 0
    while i < len(lines):
        if i in consumed:
            i += 1
            continue
        if i in fenced:
            start, end, _info = fenced[i]
            if start in mermaid:
                flush()
                segments.append(mermaid[start])
            else:
                text.extend(lines[start:end + 1])
            prose.append("")  # a fence still ends the paragraph before it
            i = end + 1
            continue
        line = lines[i]
        matches = _images_in(line)
        if not matches:
            text.append(line)
            prose.append(line)
            i += 1
            continue
        last = 0
        for n, m in enumerate(matches):
            if line[last:m.start()].strip():
                text.append(line[last:m.start()].strip())
            flush()
            segments.append(_image(m, described.get(i, "") if n == 0 else ""))
            last = m.end()
        if line[last:].strip():
            text.append(line[last:].strip())
        starts = [0] + [m.end() for m in matches]
        ends = [m.start() for m in matches] + [len(line)]
        rest = "".join(line[a:b] for a, b in zip(starts, ends))
        if rest.strip():  # a line left blank by removing a reference is dropped
            prose.append(rest)
        i += 1
    flush()
    return segments, "\n".join(prose), len(fences), sum(e - s - 1 for s, e, _ in fences)


def segments(body: str, limit: int | None = None) -> list[dict]:
    """The body as text, image and mermaid segments, in order. Never raises.

    With ``limit``, at most that many image and mermaid segments; the rest of
    the body, from the line holding the next figure, is one text segment.
    """
    return _parse(body if isinstance(body, str) else "", limit)[0]


# --- measurement -------------------------------------------------------------

def _unquoted(text: str) -> str:
    """``text`` with each quoted span on a line replaced by a space (C2).

    A span opens at a straight or a curly opening quote and runs to the next
    matching close on the same line, whatever opens inside it: ``“a — “b” c”``
    hides its dash. An opener with no close on its line is plain text. Linear:
    a straight quote with no close has no later straight quote on the line
    either, and after one curly opener misses, no later one is tried.
    """
    out = []
    for line in text.split("\n"):
        kept, pos, curly = [], 0, True
        for m in _QUOTE_OPEN.finditer(line):
            start, straight = m.start(), m.group() == '"'
            if start < pos or not (straight or curly):
                continue
            end = line.find('"' if straight else "”", start + 1)
            if end == -1:
                curly = curly and straight
                continue
            kept.append(line[pos:start])
            pos = end + 1
        kept.append(line[pos:])
        out.append(" ".join(kept))
    return "\n".join(out)


def _ends(token: str) -> bool:
    """Whether a prose token ends a sentence: a final . ! or ?, past any closing quote or bracket."""
    token = token.rstrip("\"'”’)]}")
    return token.endswith((".", "!", "?")) and token.lower() not in _ABBREVIATIONS


def _setext(prose_lines: list[str]) -> int:
    """Setext underlines: a ``=`` or ``-`` line right under a plain prose line."""
    return sum(
        1 for above, line in zip(prose_lines, prose_lines[1:])
        if _SETEXT.fullmatch(line) and above.strip() and not _SETEXT.fullmatch(above)
        and not _BULLET.match(above) and not _HEADER.match(above)
    )


def measure(body: str, role: str = "reviewer") -> dict:
    """The metrics of one turn's prose (C2). Pure and never raises on any str."""
    body = body if isinstance(body, str) else ""
    segs, prose, fences, fenced_lines = _parse(body)
    plain = _INLINE_CODE.sub(" ", prose)  # prose outside inline code
    unquoted = _unquoted(plain)
    # Quoting the artifact is not the speaker's own writing: its bold and its
    # sentence ends are the artifact's, in double or single quotes.
    quoted = _SINGLE.sub(" ", unquoted)
    lines = [line for line in prose.splitlines() if line.strip()]
    low = prose.lower()
    words = len(prose.split())
    sentences = sum(1 for t in quoted.split() if _ends(t))
    first = lines[0].split() if lines else []
    first_sentence = next((i + 1 for i, t in enumerate(first) if _ends(t)), len(first))
    images = [
        {"kind": s["kind"], "name": s.get("name", ""), "ref": s.get("ref", ""),
         "caption": s["caption"], "description": s["description"], "ok": s.get("ok")}
        for s in segs if s["kind"] in ("image", "mermaid")
    ]
    tells = {key: len(pattern.findall(prose)) for key, pattern in _TELLS.items()}
    tells["preempt"] = sum(low.count(p) for p in _PREEMPT)
    tells["filler"] = sum(low.count(p) for p in FILLER)
    em, en = unquoted.count("—"), unquoted.count("–")
    path_line = sum(1 for _ in _PATH_LINE.finditer(body))
    section = sum(1 for _ in _SECTION.finditer(prose))
    own = "\n".join(line for line in quoted.split("\n") if not _BLOCKQUOTE.match(line))
    return {
        "kind": kind(role),
        "words": words,
        # the first sentence of the first line: the point a reader meets first
        "first_line_words": first_sentence,
        "lines": len(lines),
        "longest_paragraph_words": max(
            (len(p.split()) for p in re.split(r"\n\s*\n", prose)), default=0
        ),
        "sentences": max(sentences, 1) if words else 0,
        "em_dashes": em,
        "en_dashes": en,
        "dashes": em + en,
        "bold": len(_BOLD.findall(own)),
        "headers": sum(1 for line in lines if _HEADER.match(line)) + _setext(prose.split("\n")),
        "tables": sum(1 for line in lines if _TABLE.fullmatch(line.strip())),
        "bullets": sum(1 for line in lines if _BULLET.match(line)),
        "nested_bullets": sum(1 for line in lines if _BULLET.match(line) and _NESTED.match(line)),
        "fenced_lines": fenced_lines,
        "images": images[:IMAGE_RECORDS],
        "images_count": len(images),
        "images_uncaptioned": sum(
            1 for im in images
            if not im["caption"] or not im["description"]
            or len(im["caption"].split()) > _CAPTION_WORDS
            or len(im["description"].split()) > _DESCRIPTION_WORDS
        ),
        "pointers_path_line": path_line,
        "pointers_section": section,
        "pointers": path_line + section,
        "examples": (
            sum(low.count(p) for p in _EXAMPLE_PHRASES)
            + len(_INLINE_CODE.findall(prose))
            + fences
            + sum(1 for _ in _UNIT.finditer(prose))
        ),
        "tells": tells,
        "filler_hits": sum(tells.values()),
        "cap": cap_for(role),
        "rules_version": RULES_VERSION,
    }


def _magic_ok(head: bytes, name: str) -> bool:
    if name.endswith(".png"):
        return head.startswith(_PNG)
    text = head[3:] if head.startswith(b"\xef\xbb\xbf") else head
    return text.lstrip().startswith((b"<svg", b"<?xml"))


def _own_file(image: dict, images_dir, base: str) -> str | None:
    """The sha256 of the speaker's own image file when it passes, else None."""
    name = str(image.get("name") or "")
    if not base or image.get("ref") != "images/" + name:
        return None
    if name not in (f"{base}.svg", f"{base}.png"):
        return None
    try:
        fd = os.open(os.path.join(images_dir, name), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except (OSError, TypeError, ValueError):
        return None  # missing, or a symlink (ELOOP)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > IMAGE_MAX_BYTES:
            return None
        with open(fd, "rb", closefd=False) as handle:
            data = handle.read(IMAGE_MAX_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    if len(data) > IMAGE_MAX_BYTES or not _magic_ok(data[:512], name):
        return None  # grew past the cap since the fstat, or not a PNG or an SVG
    return hashlib.sha256(data).hexdigest()


def check_images(images: list[dict], images_dir, base: str) -> list[dict]:
    """Copies of ``images`` with ``ok`` filled in (C3). The one IO step; never raises.

    A mermaid image is ok. A file image is ok only when it is referenced as
    exactly ``images/<name>``, the name is this speaker's own ``{base}.svg`` or
    ``{base}.png``, and it is a regular file of at most IMAGE_MAX_BYTES whose
    first bytes are a PNG or an SVG. A passing file image also records
    ``sha256``, of the exact bytes read here, so the view can ask the server
    for those bytes and no later overwrite.
    """
    out = []
    for image in images or []:
        image = dict(image)
        image.pop("sha256", None)
        digest = None if image.get("kind") == "mermaid" else _own_file(image, images_dir, base)
        image["ok"] = image.get("kind") == "mermaid" or digest is not None
        if digest is not None:
            image["sha256"] = digest
        out.append(image)
    return out


# --- rules -------------------------------------------------------------------

def _image_count(metrics: dict) -> int:
    """Every image the take held: ``images`` keeps only the first IMAGE_RECORDS."""
    return max(len(metrics.get("images") or []), _num(metrics.get("images_count")) or 0)


def _filler(metrics: dict) -> int:
    tells = metrics.get("tells")
    return (_num(tells.get("filler")) or 0) if isinstance(tells, dict) else 0


def violations(metrics: dict, role: str) -> list[str]:
    """The hard rules a take broke, in C5 order. Any one forces a retake."""
    k = kind(role)
    images = metrics.get("images") or []
    checks = (
        ("over_cap", metrics.get("words", 0) > cap_for(role)),
        ("multi_line", k == "junior_ic" and metrics.get("lines", 0) > 1),
        ("multi_sentence", k == "junior_ic" and metrics.get("sentences", 0) > 1),
        ("headers", metrics.get("headers", 0) > 0),
        ("bold", metrics.get("bold", 0) > 0),
        ("tables", metrics.get("tables", 0) > 0),
        ("nested", metrics.get("nested_bullets", 0) > 0),
        ("too_many_bullets", metrics.get("bullets", 0) > MAX_BULLETS.get(k, _BULLETS)),
        ("too_many_images", _image_count(metrics) > _IMAGES[k]),
        ("image_uncaptioned", metrics.get("images_uncaptioned", 0) > 0),
        ("image_missing", any(im.get("kind") == "image" and not im.get("ok") for im in images)),
        ("action_too_long",
         k == "owner" and (metrics.get("action_chars") or 0) > turnblock.ACTION_MAX),
        # Only the owner and the reviewers are asked for a stance.
        ("stance_too_long",
         k in {"owner", "reviewer"} and (metrics.get("stance_chars") or 0) > turnblock.STANCE_MAX),
        ("filler", _filler(metrics) > _FILLER_MAX),
    )
    return [slug for slug, broke in checks if broke]


def flags(metrics: dict, role: str) -> list[str]:
    """What is measured and shown but never forces a retake, in C5 order."""
    k = kind(role)
    tells = metrics.get("tells") if isinstance(metrics.get("tells"), dict) else {}
    checks = (
        ("no_pointer", k in ("owner", "reviewer") and not metrics.get("pointers")),
        ("no_example", k in ("owner", "reviewer") and not metrics.get("examples")),
        ("dashes", metrics.get("dashes", 0) > 0),
        ("long_first_line", metrics.get("first_line_words", 0) > _FIRST_LINE_WORDS),
        ("stance_clipped", (metrics.get("stance_chars") or 0) > turnblock.STANCE_MAX),
        ("tells", any((_num(tells.get(t)) or 0) > 0 for t in _SOFT_TELLS)),
    )
    return [slug for slug, on in checks if on]


def _said(slug: str, m: dict, image: str = "") -> str:
    k = m.get("kind", "reviewer")
    return {
        "over_cap": f"{m.get('words', 0)} words (cap {m.get('cap', 0)})",
        "multi_line": f"{m.get('lines', 0)} lines (one allowed)",
        "multi_sentence": f"{m.get('sentences', 0)} sentences (one allowed)",
        "headers": f"{m.get('headers', 0)} headers",
        "bold": f"{m.get('bold', 0)} bold",
        "tables": f"{m.get('tables', 0)} tables",
        "nested": f"{m.get('nested_bullets', 0)} nested bullets",
        "too_many_bullets": f"{m.get('bullets', 0)} bullets (max {MAX_BULLETS.get(k, _BULLETS)})",
        "too_many_images": f"{_image_count(m)} images (max {_IMAGES.get(k, 1)})",
        "image_uncaptioned": "a caption over 15 words, a description over 40, or either missing",
        # The reference the master would pass, when this speaker was offered one.
        "image_missing": (f"an image not at images/{image}.svg or .png" if image
                          else "an image missing or not your own file"),
        "action_too_long": f"action {m.get('action_chars', 0)} characters (max {turnblock.ACTION_MAX})",
        "stance_too_long": f"stance {m.get('stance_chars', 0)} characters (max {turnblock.STANCE_MAX})",
        "filler": f"{_filler(m)} filler phrases",
    }.get(slug, slug)


def note(metrics: dict, violations: list[str], take: int, *, image: str = "") -> str:
    """The retake paragraph a speaker is handed. cast.goal clips it to RETAKE_NOTE_MAX.

    The image rules come first: a speaker cannot reread their way to what the
    master found wrong with a file, so a longer list that the clip cuts loses a
    count the speaker can see for themselves. ``image`` is the stem the speaker
    was offered (its goal's ``image``); ``image_missing`` then names the one
    reference that would pass.
    """
    ordered = sorted(violations, key=lambda v: "image" not in v)
    said = "; ".join(_said(v, metrics, image) for v in ordered)
    return f"Retake {take} of {MAX_TAKES}. Rules broken: {said}. Say it again within them."


# --- the run -----------------------------------------------------------------

def _pct(n: int, d: int) -> float | None:
    return None if d == 0 else round(100 * n / d, 1)


def _median(values: list) -> float | None:
    return float(statistics.median(values)) if values else None


def _num(value: object) -> int | float | None:
    """``value`` when it is a finite number and not a bool, otherwise None.

    json.loads reads NaN, Infinity and a 400-digit int, and a hand-edited row
    can hold a string or a list: none may raise out of the view route or eval,
    or reach a payload served with allow_nan=False.
    """
    try:
        return value if not isinstance(value, bool) and math.isfinite(value) else None
    except (TypeError, OverflowError):  # not a number; an int too big for a float
        return None


def _takes(doc: dict) -> int:
    t = doc.get("takes")
    return t if isinstance(t, int) and not isinstance(t, bool) and t >= 1 else 1


def summary(rows: Iterable[tuple[str, dict]]) -> dict | None:
    """C11 over kept reductions: ``turn`` and ``decision`` rows whose ``voice`` is a dict.

    Every other kind (``take``, and later loops' kinds) is left out by
    construction. None when no row was measured, which is a pre-voice run.
    """
    kept = [
        (k, d) for k, d in rows
        if k in ("turn", "decision") and isinstance(d, dict)
        and isinstance(d.get("voice"), dict) and d["voice"]
    ]
    if not kept:
        return None
    turns = [d for k, d in kept if k == "turn"]
    decisions = [d for k, d in kept if k == "decision"]
    role = lambda d: d.get("role") if isinstance(d.get("role"), str) else ""  # noqa: E731
    OR = [d for d in turns if kind(role(d)) in ("owner", "reviewer")]
    R = [d for d in turns if kind(role(d)) == "reviewer"]
    J = [d for d in turns if kind(role(d)) == "junior_ic"]
    C = decisions[-1:]
    ALL = OR + J + C
    v = lambda d: d["voice"]  # noqa: E731
    n = lambda d, key: _num(v(d).get(key)) or 0  # noqa: E731
    tells = lambda d: v(d)["tells"] if isinstance(v(d).get("tells"), dict) else {}  # noqa: E731

    groups: dict[str, list[dict]] = {}
    for d in OR + J:
        groups.setdefault(role(d), []).append(d)
    if C:
        groups["chair"] = C
    chair = v(C[0]) if C else None
    return {
        "owner_reviewer_median_words": _median([n(d, "words") for d in OR]),
        "owner_reviewer_pct_within_cap": _pct(
            sum(1 for d in OR if n(d, "words") <= (n(d, "cap") or CAPS["reviewer"])), len(OR)),
        "median_words_by_role": {r: _median([n(d, "words") for d in ds]) for r, ds in groups.items()},
        "chair_words": _num(chair.get("words")) if chair else None,
        "chair_headers": _num(chair.get("headers")) if chair else None,
        "chair_tables": _num(chair.get("tables")) if chair else None,
        "junior_turns": len(J),
        "junior_pct_compliant": _pct(sum(
            1 for d in J
            if n(d, "words") <= CAPS["junior_ic"] and n(d, "lines") == 1 and n(d, "sentences") == 1
        ), len(J)),
        "pct_clean_format": _pct(sum(
            1 for d in ALL
            if n(d, "bold") + n(d, "headers") + n(d, "tables") + n(d, "nested_bullets") == 0
        ), len(ALL)),
        "pct_first_line_le_25": _pct(
            sum(1 for d in OR if n(d, "first_line_words") <= _FIRST_LINE_WORDS), len(OR)),
        "unquoted_dashes": sum(n(d, "dashes") for d in ALL),
        "reviewer_pct_with_pointer": _pct(sum(1 for d in R if n(d, "pointers") > 0), len(R)),
        "max_turn_refs": max((_num(tells(d).get("turn_refs")) or 0 for d in ALL), default=0),
        "unchanged_mentions_junior_chair": sum(
            _num(tells(d).get("unchanged")) or 0 for d in J + C),
        "total_takes": sum(_takes(d) for d in ALL),
        "retakes_by_role": {r: sum(_takes(d) - 1 for d in ds) for r, ds in groups.items()},
        "kept_flagged": sum(1 for d in ALL if d.get("violations")),
    }
