"""committee-eval: how good or bad was one finished committee review?

A second playbook over the committee's own record. For one finished committee
run it gives six scores, each backed by evidence the master checked: three from
an LLM judge whose every quote must verify against a pinned snapshot
(verdict_grounded, edits_address_concerns, concern_coverage), and three computed
straight from the record (efficiency, concision, verdict_consistency). It reads
the target strictly read-only, and it never gates or feeds the accept/reject
ruling.

Every dimension carries a version, so a score is only ever compared with scores
taken under the same definition. The voice rules and the one word counter live
in playbooks/committee/voice.py; this module imports only ``RULES`` and
``measure`` from it, so there is never a second definition to drift.

Stdlib-only.
"""
from __future__ import annotations

import hashlib
import json

from playbooks.committee.voice import RULES, measure

# D5 order. A loop that changes a dimension's definition, bands or inputs bumps its n.
DIMENSIONS: dict[str, str] = {
    "verdict_grounded": "verdict_grounded@1",
    "edits_address_concerns": "edits_address_concerns@1",
    "concern_coverage": "concern_coverage@1",
    "efficiency": "efficiency@1",
    "concision": "concision@1",
    "verdict_consistency": "verdict_consistency@1",
}
JUDGE_DIMS = ("verdict_grounded", "edits_address_concerns", "concern_coverage")
DETERMINISTIC_DIMS = ("efficiency", "concision", "verdict_consistency")

MIN_ANCHORS = 2  # anchored targets a judge dimension needs before it can read calibrated (D8)
QUOTE_MAX = 300  # a judge quote is clipped to this many characters before it is verified (C3)
EVIDENCE_MAX = 5  # evidence items kept per judge dimension; extras are dropped (C3)
FENCE_TAG = "hermes-eval"

VERBATIM = (
    "every quote is verbatim and contiguous from the place it cites "
    "(no ellipses, no paraphrase)"
)

# The D5 judge anchors, written to inputs/rubric.md under the version lines.
# D5's closing note on run-9's expected absent stakeholders is left out: it is
# an acceptance note about one run, and telling the judge would bias every run.
RUBRIC = "\n".join((
    "verdict_grounded",
    "5: every claim in the chair prose traces to a turn or to the document, and the "
    "verdict follows from the arguments.",
    "3: mostly grounded, with some unsupported claims.",
    "1: asserts things nobody said, or contradicts the thread.",
    "",
    "edits_address_concerns",
    "5: each edit does what its delegation asked and resolves the concern behind it.",
    "3: partial.",
    "1: cosmetic, partial or unrelated edits.",
    "Read the per-edit snapshots under inputs/doc/ when present; cite the delegating "
    'owner turn, the junior_ic report, or the edited text itself (`where:"original"|"revised"`, C3).',
    "",
    "concern_coverage",
    "5: every seated member's main concerns were answered by the owner or by an edit, "
    "and the thread names no needed stakeholder missing from the room.",
    "1: major concerns went unanswered, or a missing function is named repeatedly.",
    "Concerns come from each member's own turns, never from persona config. The judge "
    "also gets `seats`, `unanswered_reviewer_turns` and `outside_room_mentions`.",
    "",
    f"Evidence: {VERBATIM}.",
))

_WALL_WORDS = 120  # C8: a wall is a paragraph over 120 words (voice.WALL_WORDS; D11 imports only RULES and measure)


def words(text: str) -> int:
    """The one word count, voice's, so eval never grows a second counter."""
    return measure(text)["words"]


def _num(row: object, key: str) -> int | float:
    """A measure value, or 0 when the row or the value is not a number (reduce never raises)."""
    value = row.get(key) if isinstance(row, dict) else None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def voice_shares(rows: list[dict]) -> dict:
    """C8's four shares over the measured population P, one measure dict per turn.

    n = |P|. Each share is rounded to 4 dp, and every share is None when n == 0.
    """
    n = len(rows)
    if n == 0:
        return {"n": 0, "pointer_share": None, "walls_share": None,
                "example_share": None, "filler_per_turn": None}
    return {
        "n": n,
        "pointer_share": round(sum(_num(r, "pointers") >= 1 for r in rows) / n, 4),
        "walls_share": round(sum(_num(r, "longest_paragraph_words") > _WALL_WORDS for r in rows) / n, 4),
        "example_share": round(sum(_num(r, "examples") >= 1 for r in rows) / n, 4),
        "filler_per_turn": round(sum(_num(r, "filler_hits") for r in rows) / n, 4),
    }


def dimension_versions(rules: tuple[str, ...] = RULES) -> dict[str, str]:
    """DIMENSIONS, with concision tied to the voice rules it scores against.

    concision gains "+" and the first 8 hex of sha256 over the rules, so a rules
    swap moves its version and an old concision score can never silently compare.
    """
    digest = hashlib.sha256("\n".join(rules).encode()).hexdigest()[:8]
    return {**DIMENSIONS, "concision": DIMENSIONS["concision"] + "+" + digest}


def rubric_version(versions: dict[str, str]) -> str:
    """One id for a whole set of dimension versions: "r" and 8 hex."""
    return "r" + hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()[:8]
