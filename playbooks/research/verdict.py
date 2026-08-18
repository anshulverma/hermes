"""A machine-readable verdict, carried inside the agent's prose.

The transport hands the master exactly one thing from a worker: its final text,
under ``answer``. Anything structured has to travel inside that text.

The obvious approach -- read the verdict out of the prose -- does not work.
Measured against seventeen real syntheses, matching the words a reviewer would
use found ten candidates of which two were verdicts; the rest were ordinary
adjectives: "the **blocking** window is bounded by a 90-minute lease",
"**blocking** DCP saves go 102 to 201", "not a **clean** kill", "CI is
**clean**". Colouring on that paints working changes red and calls a failed
check green, and in a review tool a colour is read as a verdict.

So the agent is asked for one instead, in a fenced block with its own tag. That
is unambiguous both ways: present and parseable, or absent. **Absent stays
absent** -- an item with no verdict is reported as unstated, never inferred.
Seven of those seventeen syntheses genuinely had none, and saying so is the
honest reading.

Stdlib-only.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

# The info string on the fence. Deliberately not `json`: an agent writes plenty
# of ordinary JSON blocks, and only this tag means "this is my verdict".
FENCE_TAG = "hermes-verdict"

# The closed vocabulary, worst first. Anything else is not a verdict -- an agent
# inventing a word must not become a colour nobody defined.
VERDICTS: tuple[str, ...] = ("blocking", "needs-discussion", "clean")

# A headline rides in a table row, so it has to fit on one line.
HEADLINE_MAX = 160

_BLOCK_RE = re.compile(
    r"```[ \t]*" + re.escape(FENCE_TAG) + r"[ \t]*\n(.*?)\n?```",
    re.DOTALL | re.IGNORECASE,
)


def parse(answer: Optional[str]) -> Optional[dict]:
    """The verdict an answer carries, or None when it carries none.

    The last block wins: an agent that restates its verdict has settled on the
    later one. Only known keys survive, and only a known verdict word counts.
    """
    if not isinstance(answer, str) or not answer:
        return None

    blocks = _BLOCK_RE.findall(answer)
    for raw in reversed(blocks):
        parsed = _one(raw)
        if parsed is not None:
            return parsed
    return None


def _one(raw: str) -> Optional[dict]:
    """One candidate block as a verdict, or None if it is not one."""
    try:
        doc = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None

    word = doc.get("verdict")
    if not isinstance(word, str):
        return None
    word = word.strip().lower()
    if word not in VERDICTS:
        return None

    out: dict[str, Any] = {"verdict": word}
    headline = doc.get("headline")
    if isinstance(headline, str) and headline.strip():
        out["headline"] = headline.strip()[:HEADLINE_MAX]
    return out


def strip(answer: Optional[str]) -> str:
    """The answer with its verdict block removed.

    The verdict is rendered as its own element, so leaving the raw JSON in the
    prose only shows the reader plumbing. Ordinary code blocks are untouched --
    the tag is what identifies this one.
    """
    if not isinstance(answer, str) or not answer:
        return ""
    return _BLOCK_RE.sub("", answer).strip()


def instruction() -> str:
    """What to tell an agent so that ``parse`` can read it back.

    Kept terse on purpose. This rides in every goal, and a goal has a hard
    character budget it shares with the material being judged -- a wordier
    instruction buys nothing and costs the agent the context it needs.

    It still spends words saying that omitting the block is allowed: an agent
    pushed to always pick a verdict will pick one, and an invented verdict is
    worse than a missing one.
    """
    return (
        "\n\nEnd with a verdict block, nothing after it:\n\n"
        f"```{FENCE_TAG}\n"
        '{"verdict": "needs-discussion", "headline": "one line a reader must '
        'know"}\n'
        "```\n\n"
        "verdict: `blocking` (must be fixed before this lands), "
        "`needs-discussion` (a real question for the author), `clean` "
        "(neither). Omit the block if the material does not let you judge -- "
        "unstated is reported as unstated; do not guess."
    )
