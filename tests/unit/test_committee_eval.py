"""Tests for committee-eval (playbooks/committee/eval.py) and its voice seam.

TDD: written FIRST, watched fail, then the module implemented.

The eval scores one finished committee run on six dimensions, and every number
it reports has to come from the record or from a quote the master verified. So
these tests pin each rule on fixed inputs and, from the fixtures on, on two real
runs frozen under tests/data/committee-eval/. No test reads ~/.hermes, /data or
the repo's docs/.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import urllib.parse
from contextlib import closing
from pathlib import Path

from engine.db.migrate import apply_migrations
from playbooks.committee import eval as E
from playbooks.committee import voice

MEASURE_KEYS = {"words", "pointers", "examples", "longest_paragraph_words", "filler_hits"}


def _w(k: int) -> str:
    return " ".join(["w"] * k)


def test_voice_measure_and_version():
    """T17: voice.measure and the C8 shares on fixed inputs; a rules change moves concision's version, and only it."""
    # Every key, all ints; empty and non-str input count as "" and never raise.
    empty = dict.fromkeys(MEASURE_KEYS, 0)
    assert voice.measure("") == empty
    for junk in (None, 42, b"a b", ["a b"]):
        assert voice.measure(junk) == empty
    m = voice.measure("a b  c\n\nd", role="owner")
    assert set(m) == MEASURE_KEYS and all(type(v) is int for v in m.values())
    assert m["words"] == 4 and E.words("a b  c\n\nd") == 4

    # A paragraph is a maximal run of non-blank lines; a wall is more than 120 words.
    assert voice.WALL_WORDS == 120
    assert voice.measure(_w(120))["longest_paragraph_words"] == 120
    assert voice.measure(_w(60) + "\n" + _w(61))["longest_paragraph_words"] == 121
    assert voice.measure(_w(100) + "\n  \n" + _w(21))["longest_paragraph_words"] == 100

    # Pointers: a path:line (with a range) and a section, in both spellings.
    assert voice.measure("See playbooks/committee/eval.py:12-14, §3.2 and Section 5.1.")["pointers"] == 3
    assert voice.measure("file.py:12-14")["pointers"] == 1
    assert voice.measure("§3.2")["pointers"] == 1
    assert voice.measure("line 12 of the file")["pointers"] == 0

    # Examples: 2 phrases + 1 inline span (the one inside the fence is not counted)
    # + 1 fenced block + 1 number with a unit.
    ex = voice.measure(
        "For example, e.g. the `retry` flag cuts p99 by 200 ms.\n"
        "\n"
        "```python\n"
        "call(`inside`)\n"
        "```\n"
    )
    assert ex["examples"] == 5
    assert voice.measure("Plain words only.")["examples"] == 0

    # Filler: C8's 15 phrases in order, each a case-insensitive substring.
    assert voice.FILLER == (
        "great question", "it's worth noting", "it is worth noting", "to be clear",
        "let me be clear", "i want to be clear", "at the end of the day", "that said",
        "happy to", "i'd be happy", "in summary", "to summarize", "hope this helps",
        "let's dive", "delve",
    )
    filler = voice.measure("Great question. That said, I delved in; to be clear, I'd be happy to help.")
    # great question, that said, delve (inside "delved"), to be clear, i'd be happy, happy to
    assert filler["filler_hits"] == 6

    # RULES: one line per element, no bold, no long dashes, no heading.
    assert voice.RULES and isinstance(voice.RULES, tuple)
    for rule in voice.RULES:
        assert isinstance(rule, str) and rule.strip()
        assert "**" not in rule and "\u2013" not in rule and "\u2014" not in rule
        assert "\n" not in rule and not rule.startswith("#")

    # The C8 shares over fixed rows, and over nothing.
    rows = [
        {"words": 9, "pointers": 1, "examples": 0, "longest_paragraph_words": 121, "filler_hits": 2},
        {"words": 9, "pointers": 0, "examples": 3, "longest_paragraph_words": 120, "filler_hits": 1},
        {"words": 9, "pointers": 2, "examples": 1, "longest_paragraph_words": 5, "filler_hits": 0},
    ]
    assert E.voice_shares(rows) == {
        "n": 3, "pointer_share": 0.6667, "walls_share": 0.3333,
        "example_share": 0.6667, "filler_per_turn": 1.0,
    }
    assert E.voice_shares([]) == {
        "n": 0, "pointer_share": None, "walls_share": None,
        "example_share": None, "filler_per_turn": None,
    }
    assert E.voice_shares([{}, {"pointers": "2", "filler_hits": None}]) == {
        "n": 2, "pointer_share": 0.0, "walls_share": 0.0,
        "example_share": 0.0, "filler_per_turn": 0.0,
    }
    assert E.voice_shares([voice.measure(_w(121)), voice.measure(_w(120))])["walls_share"] == 0.5

    # The rubric's identity: six dimensions in D5 order, all @1, and the judge anchors.
    assert tuple(E.DIMENSIONS) == E.JUDGE_DIMS + E.DETERMINISTIC_DIMS == (
        "verdict_grounded", "edits_address_concerns", "concern_coverage",
        "efficiency", "concision", "verdict_consistency",
    )
    assert all(v == f"{k}@1" for k, v in E.DIMENSIONS.items())
    assert (E.MIN_ANCHORS, E.QUOTE_MAX, E.EVIDENCE_MAX, E.FENCE_TAG) == (2, 300, 5, "hermes-eval")
    assert E.VERBATIM in E.RUBRIC and all(d in E.RUBRIC for d in E.JUDGE_DIMS)

    # A rules swap moves concision's version and the rubric version, and nothing else.
    now = E.dimension_versions()
    digest = hashlib.sha256("\n".join(voice.RULES).encode()).hexdigest()[:8]
    assert now == {**E.DIMENSIONS, "concision": "concision@1+" + digest}
    assert E.DIMENSIONS["concision"] == "concision@1"
    swapped = E.dimension_versions(voice.RULES + ("Say it in one line.",))
    assert swapped["concision"] != now["concision"]
    assert {k: v for k, v in swapped.items() if k != "concision"} == {
        k: v for k, v in now.items() if k != "concision"
    }
    assert E.rubric_version(now) == "r" + hashlib.sha256(
        json.dumps(now, sort_keys=True).encode()
    ).hexdigest()[:8]
    assert re.fullmatch(r"r[0-9a-f]{8}", E.rubric_version(now))
    assert E.rubric_version(swapped) != E.rubric_version(now)


# --- the two real baselines, frozen (tests/data/committee-eval/) -------------
# run-9 (~/.hermes) and run-2 (committee-spin/home), extracted once, read-only.
# Tests build a throwaway home from them and never read ~/.hermes, /data or docs/.

EVAL_FIXTURES = Path(__file__).resolve().parents[1] / "data" / "committee-eval"
RUN2_REDUCTIONS = EVAL_FIXTURES.parent / "committee-run-2-reductions.json"
ARTIFACT_LINE = re.compile(r"^((?:\*\*)?Artifact:(?:\*\*)?\s*)(.*)$")
RUN9_DOC = ["00-original.md"] + [f"t{n:02d}.md" for n in range(3, 25, 3)]


def _insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    cols, marks = ", ".join(row), ", ".join("?" * len(row))
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))


def build_home(tmp_path: Path, name: str) -> tuple[Path, str]:
    """Build ``tmp_path/"home"`` holding one frozen baseline, ``"run-9"`` or ``"run-2"``.

    Rows go in by column name with their ids kept. run-2's reductions come from
    the shared committee-run-2-reductions.json. thread.md, revised/, doc/ and
    traces/ land under home/runs/<id>/, and the original is copied to
    ``tmp_path/"artifact"/"federation-future.md"``, which keeps the basename so
    revised/ and snapshot_key still derive from it. Every reduction ``artifact``
    and the thread.md ``Artifact:`` line (same line index, same label form) are
    rewritten to that copy, so pinned line numbers hold and nothing names the
    real host. Returns ``(home, run_id)``. Call once per ``tmp_path``.
    """
    src = EVAL_FIXTURES / name
    run = json.loads((src / "run.json").read_text(encoding="utf-8"))
    run_id = run["id"]
    home = tmp_path / "home"
    run_dir = home / "runs" / run_id
    run_dir.mkdir(parents=True)
    original = tmp_path / "artifact" / "federation-future.md"
    original.parent.mkdir()
    shutil.copyfile(src / "artifact" / "federation-future.md", original)
    for sub in ("revised", "doc", "traces"):
        if (src / sub).is_dir():
            shutil.copytree(src / sub, run_dir / sub)

    lines = (src / "thread.md").read_bytes().decode("utf-8").split("\n")
    idx = next(i for i, line in enumerate(lines) if ARTIFACT_LINE.match(line))
    lines[idx] = ARTIFACT_LINE.match(lines[idx]).group(1) + str(original)
    (run_dir / "thread.md").write_bytes("\n".join(lines).encode("utf-8"))

    if name == "run-2":  # the shared JSON holds {phase, kind, json-as-object} only
        reductions = [
            {"run_id": run_id, "kind": r["kind"], "phase": r["phase"],
             "json": json.dumps(r["json"], ensure_ascii=False),
             "created_at": run["created_at"], "updated_at": run["created_at"]}
            for r in json.loads(RUN2_REDUCTIONS.read_text(encoding="utf-8"))
        ]
    else:
        reductions = json.loads((src / "reductions.json").read_text(encoding="utf-8"))
    for r in reductions:
        doc = json.loads(r["json"])
        if isinstance(doc, dict) and "artifact" in doc:
            doc["artifact"] = str(original)
            r["json"] = json.dumps(doc, ensure_ascii=False)

    db = home / "queue.db"
    apply_migrations(str(db))
    with closing(sqlite3.connect(str(db))) as conn:
        _insert(conn, "runs", run)
        for r in reductions:
            _insert(conn, "reductions", r)
        for table in ("tickets", "attempts"):
            for row in json.loads((src / f"{table}.json").read_text(encoding="utf-8")):
                _insert(conn, table, row)
        conn.commit()
    return home, run_id


def test_fixture_homes_build(tmp_path):
    for name, n_attempts in (("run-9", 25), ("run-2", 21)):
        base = tmp_path / name
        base.mkdir()
        home, run_id = build_home(base, name)
        src, run_dir = EVAL_FIXTURES / name, home / "runs" / name
        copy = base / "artifact" / "federation-future.md"
        assert run_id == name
        assert copy.read_bytes() == (src / "artifact" / "federation-future.md").read_bytes()

        uri = "file:" + urllib.parse.quote(str(home / "queue.db")) + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            attempt_ids = [r["id"] for r in conn.execute(
                "SELECT a.id FROM attempts a JOIN tickets t ON a.ticket_id = t.id"
                " WHERE t.run_id = ? ORDER BY a.id", (run_id,))]
            docs = [json.loads(r["json"]) for r in conn.execute(
                "SELECT json FROM reductions WHERE run_id = ? ORDER BY id", (run_id,))]
        assert run is not None and run["playbook"] == "committee"
        assert len(attempt_ids) == n_attempts
        traces = run_dir / "traces"
        assert sorted(int(p.stem) for p in traces.iterdir()) == attempt_ids
        for trace in traces.iterdir():  # trimmed: only what the eval reads (G4)
            for line in trace.read_bytes().splitlines():
                obj = json.loads(line)
                if obj["type"] == "cost-state":
                    assert set(obj) <= {"type", "totalCostUSD"}
                else:
                    assert obj["type"] == "assistant" and set(obj) == {"type", "message"}
                    assert set(obj["message"]) <= {"id", "usage"}

        want = (src / "thread.md").read_bytes().decode("utf-8").split("\n")
        got = (run_dir / "thread.md").read_bytes().decode("utf-8").split("\n")
        idx = next(i for i, line in enumerate(want) if ARTIFACT_LINE.match(line))
        assert len(got) == len(want)
        assert [i for i, (a, b) in enumerate(zip(want, got)) if a != b] == [idx]
        assert ARTIFACT_LINE.match(got[idx]).groups() == (
            ARTIFACT_LINE.match(want[idx]).group(1), str(copy))

        artifacts = [d["artifact"] for d in docs if "artifact" in d]
        assert artifacts == [str(copy)] * len(artifacts)
        assert bool(artifacts) == (name == "run-9")  # run-2's reductions carry no artifact
        assert (run_dir / "revised" / "federation-future.md").read_bytes() == (
            src / "revised" / "federation-future.md").read_bytes()
        doc_dir = run_dir / "doc"
        listed = sorted(p.name for p in doc_dir.iterdir()) if doc_dir.exists() else []
        assert listed == (RUN9_DOC if name == "run-9" else [])
