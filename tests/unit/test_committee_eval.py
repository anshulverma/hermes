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
import time
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
    assert voice.measure(_w(120))["longest_paragraph_words"] == 120
    assert voice.measure(_w(60) + "\n" + _w(61))["longest_paragraph_words"] == 121
    assert voice.measure(_w(100) + "\n  \n" + _w(21))["longest_paragraph_words"] == 100

    # Pointers: a path:line (with a range) and a section, in both spellings.
    assert voice.measure("See playbooks/committee/eval.py:12-14, §3.2 and Section 5.1.")["pointers"] == 3
    assert voice.measure("file.py:12-14")["pointers"] == 1
    assert voice.measure("§3.2")["pointers"] == 1
    assert voice.measure("line 12 of the file")["pointers"] == 0
    assert voice.measure("section 1, § 2")["pointers"] == 2

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
    assert voice.measure("40 qps 3 kb")["examples"] == 0  # units are case-sensitive
    assert voice.measure("  ```\ncode\n  ```")["examples"] == 1  # an indented fence still fences
    assert voice.measure("`a\nb`")["examples"] == 0  # inline code never spans lines
    assert voice.measure("e.g. e.g.")["examples"] == 2  # every occurrence counts

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
    assert voice.measure("delve delve")["filler_hits"] == 2

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
    assert E.voice_shares([{"pointers": True}])["pointer_share"] == 0.0  # a bool is not a number

    # The rubric's identity: six dimensions in D5 order, all @1, and the judge anchors.
    assert tuple(E.DIMENSIONS) == E.JUDGE_DIMS + E.DETERMINISTIC_DIMS == (
        "verdict_grounded", "edits_address_concerns", "concern_coverage",
        "efficiency", "concision", "verdict_consistency",
    )
    assert all(v == f"{k}@1" for k, v in E.DIMENSIONS.items())
    assert (E.MIN_ANCHORS, E.QUOTE_MAX, E.EVIDENCE_MAX, E.FENCE_TAG) == (2, 300, 5, "hermes-eval")
    assert E.VERBATIM in E.RUBRIC and all(d in E.RUBRIC for d in E.JUDGE_DIMS)
    # D5's run-9 absent-stakeholder note stays out of the judge's rubric (G13).
    assert "Security" not in E.RUBRIC and "run-9" not in E.RUBRIC
    assert hashlib.sha256(E.RUBRIC.encode()).hexdigest()[:8] == "4cf6cb0f", (
        "RUBRIC text changed: bump the affected judge dimension's version in DIMENSIONS, then re-pin this hash"
    )

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


def test_voice_measure_is_linear_on_one_long_token():
    """measure runs master-side on every take, so a 200 KB unbroken token must not go quadratic."""
    for token in ("a." * 100_000, "x" * 200_000):
        start = time.perf_counter()
        assert voice.measure(token)["pointers"] == 0
        assert time.perf_counter() - start < 2.0


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
    real host; a reduction's ``revised`` is rewritten to home/runs/<id>/revised/.
    Returns ``(home, run_id)``. Call once per ``tmp_path``.
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
            if "revised" in doc:
                doc["revised"] = str(run_dir / "revised" / original.name)
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
        for d in docs:  # no reduction names the real host (tmp_path itself may sit anywhere)
            text = json.dumps(d, ensure_ascii=False).replace(str(base), "")
            assert "/.hermes/" not in text and "/data/" not in text, text[:200]
        assert (run_dir / "revised" / "federation-future.md").read_bytes() == (
            src / "revised" / "federation-future.md").read_bytes()
        doc_dir = run_dir / "doc"
        listed = sorted(p.name for p in doc_dir.iterdir()) if doc_dir.exists() else []
        assert listed == (RUN9_DOC if name == "run-9" else [])


# --- reading the target: D2 loader, D3 parser, chair prose, answered turns ----


def _thread_text(bold: bool, selection: bool) -> tuple[str, list[str]]:
    """A small thread.md in thread.py's layout; ``selection`` adds a later loop's header and pre-t01 entries."""
    from playbooks.committee.playbook import _SIMULATION

    b = "**" if bold else ""
    lines = [
        "# Committee — run-x", "",
        f"{b}Charge:{b} Decide whether to fund it.", "",
        f"{b}Artifact:{b} /tmp/proposal.md", "",
        f"{b}Committee:{b}", "",
        "- owner — Maya Okonkwo, Staff Engineer & proposal owner",
        "- tpm — Sam Iyer, Technical Program Manager",
        "- owner — Maya Again, the first line per slug wins",
        "- junior_ic — Alex Moreau, Software Engineer",
    ]
    if selection:
        lines += [
            "- Reviewer seats: chosen below", "",
            "Seat library:",
            "- security — Security Engineer, lens: threat models", "",
            "Ground rules for every speaker:",
            "Lead with the point.", "",
            "## selection 1: Maya Okonkwo, Staff Engineer & proposal owner (owner) proposes", "",
            "- crew_owner — Crew Owner, proposed but never seated",
            "Charge: a label outside the header", "",
            "## committee seated", "",
            "- security: Security Engineer. Why: auth needs an owner.",
        ]
    lines += [
        "",
        "## turn 01 — Sam Iyer, Technical Program Manager (tpm)", "",
        "One heading inside my turn:", "",
        "## Risks", "",
        "- owner — a body line, not a seat", "",
        "## turn 02 — Maya Okonkwo, Staff Engineer & proposal owner (owner)", "",
        "Taken.", "",
        "## decision — Dana Whitfield, Senior Director of Engineering", "",
        "## Ruling: defer.", "",
        "Seven edits landed, and I read the re-check of turn 03 closely.", "",
        "- re-check of turn 03 (junior_ic): APPLIED — delegated: fix section 2", "",
        "- dropped_delegation (the turn cap cut it off, no edit was made): trim it", "",
        "- dropped_floor_requests (the review ended before their turn came): pm", "",
        "- dropped_one_on_ones (the review ended before they were held): tpm", "",
        _SIMULATION,
    ]
    return "\n".join(lines) + "\n", lines


def test_thread_parser_and_chair_prose(tmp_path):
    """T7: D3's parser and chair prose, on a synthetic thread and on both baselines."""
    from playbooks.committee.playbook import _SIMULATION

    text, lines = _thread_text(bold=True, selection=False)
    parsed = E.parse_thread(text)
    assert parsed["header"] == {"text": "\n".join(lines[:13]), "line_start": 1, "line_end": 13}
    assert parsed["labels"] == {
        "Charge": "Decide whether to fund it.", "Artifact": "/tmp/proposal.md", "Committee": ""}
    assert parsed["roster"] == ["owner", "tpm", "junior_ic"]
    # "## Risks" inside turn 01 is body, not a boundary; so is its "- owner — …" line.
    assert parsed["turns"] == {
        1: {"role": "tpm", "line_start": 14, "line_end": 21,
            "body": "One heading inside my turn:\n\n## Risks\n\n- owner — a body line, not a seat"},
        2: {"role": "owner", "line_start": 22, "line_end": 25, "body": "Taken."},
    }
    decision = parsed["decision"]
    assert (decision["line_start"], decision["line_end"]) == (26, 40) == (26, len(lines))
    assert decision["body"].startswith("## Ruling: defer.\n\nSeven edits landed")
    assert decision["body"].endswith(_SIMULATION)

    # Plain labels (voice) plus a later loop's header block and pre-t01 entries.
    text2, lines2 = _thread_text(bold=False, selection=True)
    plain = E.parse_thread(text2)
    assert plain["roster"] == parsed["roster"]  # "Seat library:" ended the block: no security
    assert plain["labels"] == parsed["labels"]  # the "Charge:" after the header is not a label
    selection = lines2.index(next(ln for ln in lines2 if ln.startswith("## selection 1:"))) + 1
    assert plain["header"]["line_end"] == selection - 1
    assert "## selection" not in plain["header"]["text"]
    assert "crew_owner" not in plain["header"]["text"]
    assert plain["turns"][1]["line_start"] == lines2.index(lines[13]) + 1 > selection
    assert [t["body"] for t in plain["turns"].values()] == [
        t["body"] for t in parsed["turns"].values()]
    assert plain["decision"]["body"] == decision["body"]

    # Chair prose: the footer and the simulation paragraph go, the chair's words stay.
    prose = E.chair_prose({"verdict": decision["body"]})
    assert prose == ("## Ruling: defer.\n\n"
                     "Seven edits landed, and I read the re-check of turn 03 closely.")
    assert "APPLIED" not in prose and "dropped_" not in prose and _SIMULATION not in prose
    assert E.chair_prose({"body": "Defer, on two conditions.", "verdict": decision["body"]}) \
        == "Defer, on two conditions."
    assert E.chair_prose({}) == E.chair_prose({"verdict": None}) == E.chair_prose(None) == ""
    assert E.parse_thread("")["turns"] == {} and E.parse_thread("")["decision"] is None
    assert E.parse_thread("")["header"] == {"text": "", "line_start": None, "line_end": None}

    # Both baselines: run-9 reads its bodies from reductions, run-2 (legacy) from thread.md.
    (tmp_path / "9").mkdir()
    (tmp_path / "2").mkdir()
    t9 = E.load_target(*map(str, build_home(tmp_path / "9", "run-9")))
    t2 = E.load_target(*map(str, build_home(tmp_path / "2", "run-2")))
    assert len(t9.thread["turns"]) == 24 and len(t2.thread["turns"]) == 20
    assert (t9.thread["turns"][1]["line_start"], t9.thread["turns"][1]["line_end"]) == (19, 38)
    assert (t9.thread["decision"]["line_start"], t9.thread["decision"]["line_end"]) == (752, 877)
    assert "\n## Ruling: approve with changes. Defer; do not fund.\n" in t9.thread["decision"]["body"]
    assert t9.thread["labels"]["Artifact"] == str(tmp_path / "9" / "artifact" / "federation-future.md")
    seats = ["owner", "senior_director", "manager", "tpm", "pm", "tl", "staff_ic",
             "data_scientist", "junior_ic"]
    assert E.roster(t9) == E.roster(t2) == seats
    assert E.reviewers(t9) == E.reviewers(t2) == seats[1:-1]
    assert E.body(t9, 1) == t9.turns[1]["body"] != ""
    assert E.body(t2, 1) == t2.thread["turns"][1]["body"]
    assert E.body(t2, 1).startswith("**Dana Whitfield — Senior Director of Engineering**")
    assert E.body(t9, 99) == E.body(t2, 99) == ""
    for target, words in ((t9, 1518), (t2, 1934)):  # C5's words.chair_prose
        prose = E.chair_prose(target.decision)
        assert E.words(prose) == words
        assert "APPLIED" not in prose and _SIMULATION not in prose


def _tree(root) -> dict:
    """Every path under root -> (mode, sha256 or "" for a directory), minus SQLite's -shm/-wal."""
    import hashlib
    import os
    import stat

    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            if name.endswith(("-shm", "-wal")):
                continue
            path = Path(dirpath) / name
            mode = os.lstat(path).st_mode
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(mode) else ""
            out[str(path.relative_to(root))] = (mode, digest)
    return out


def test_source_home_never_written(tmp_path, monkeypatch):
    """T14: reading a target creates and changes nothing, on the source home or the eval home."""
    import os

    import pytest

    eval_home = tmp_path / "eval-home"  # a HERMES_HOME that must never come into being
    monkeypatch.setenv("HERMES_HOME", str(eval_home))

    typo = tmp_path / "hoem"
    assert E.validate_target(str(typo), "run-9") == f"no queue.db in {typo}"
    assert E.connect_ro(str(typo)) is None
    assert not typo.exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert E.validate_target(str(empty), "run-9") == f"no queue.db in {empty}"
    assert list(empty.iterdir()) == []

    for name, legacy in (("run-9", False), ("run-2", True)):
        base = tmp_path / name
        base.mkdir()
        home, run_id = build_home(base, name)
        before = _tree(base)
        assert E.validate_target(str(home), run_id) is None
        target = E.load_target(str(home), run_id)
        assert _tree(base) == before, name  # byte-identical, no new path
        with closing(E.connect_ro(str(home))) as conn:  # read-only for real
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("DELETE FROM runs")

        # What the loader read, from the fixture's own files and rows.
        fixture = EVAL_FIXTURES / name
        run_row = json.loads((fixture / "run.json").read_text(encoding="utf-8"))
        copy = base / "artifact" / "federation-future.md"
        run_dir = home / "runs" / run_id
        assert (target.home, target.run_id, target.legacy) == (str(home), run_id, legacy)
        assert (target.created_at, target.state) == (run_row["created_at"], run_row["state"])
        assert target.artifact == str(copy)  # run-2's comes from the header Artifact: line
        assert target.original == copy.read_bytes()
        assert target.revised == (fixture / "revised" / "federation-future.md").read_bytes()
        assert target.revised_path == str(run_dir / "revised" / "federation-future.md")
        assert target.thread_path == str(run_dir / "thread.md")
        assert target.thread_text == (run_dir / "thread.md").read_bytes().decode("utf-8")
        assert list(target.turns) == sorted(target.turns) == list(range(1, len(target.turns) + 1))
        assert (target.duplicate_turns, target.takes, target.other_kinds) == (0, 0, {})
        assert target.decision["delivered"] is True
        traces = sorted(int(p.stem) for p in (run_dir / "traces").iterdir())
        assert [a["id"] for a in target.attempts] == traces
        assert set(target.attempts[0]) == {"id", "started_at", "ended_at", "outcome"}
        assert set(target.traces) == {a["id"] for a in target.attempts}
        assert all(isinstance(data, bytes) for data in target.traces.values())
        junior = [n for n, t in target.turns.items() if t["role"] == "junior_ic"]
        assert [s["turn"] for s in target.steps] == junior
        assert target.steps[0]["key"] == "doc/t03.md"
        assert target.steps[0]["path"] == str(run_dir / "doc" / "t03.md")
        if legacy:
            assert (target.original_source, target.original_path) == ("live", str(copy))
            assert target.review_state == "pending"
            assert all(s["data"] is None for s in target.steps)
        else:
            assert target.original_source == "snapshot"
            assert target.original_path == str(run_dir / "doc" / "00-original.md")
            rows = json.loads((fixture / "reductions.json").read_text(encoding="utf-8"))
            decisions = [r for r in rows if r["kind"] == "decision"]
            assert target.review_state == decisions[-1]["review_state"]
            assert [s["data"] for s in target.steps] == [
                (fixture / "doc" / f"t{n:02d}.md").read_bytes() for n in junior]

    # The two homes (D2), both resolved; the source home defaults to the eval home.
    link = tmp_path / "link-to-run-9"
    link.symlink_to(tmp_path / "run-9" / "home")
    assert E.eval_home() == os.path.realpath(eval_home)
    assert E.source_home({}) == E.source_home({E.ENV_HOME: ""}) == E.eval_home()
    assert E.source_home({E.ENV_HOME: str(link)}) == str((tmp_path / "run-9" / "home").resolve())
    monkeypatch.setenv(E.ENV_HOME, str(link))
    assert E.source_home() == str((tmp_path / "run-9" / "home").resolve())  # the live environment
    assert not eval_home.exists()  # no thread.path, state_dir or migrate.connect anywhere


def _mini_home(root: Path, runs: list[tuple[str, str]], reductions: list[tuple]) -> Path:
    """A throwaway home: queue.db from the migrations, holding only the given rows."""
    root.mkdir(parents=True)
    apply_migrations(str(root / "queue.db"))
    with closing(sqlite3.connect(str(root / "queue.db"))) as conn:
        for run_id, playbook in runs:
            conn.execute(
                "INSERT INTO runs (id, playbook, site, base_ref, state, phase, created_at,"
                " updated_at) VALUES (?, ?, 'local', 'main', 'running', 'decision', 1.0, 1.0)",
                (run_id, playbook))
        for run_id, kind, doc in reductions:
            conn.execute(
                "INSERT INTO reductions (run_id, kind, json, created_at, updated_at, phase)"
                " VALUES (?, ?, ?, 1.0, 1.0, ?)",
                (run_id, kind, doc if isinstance(doc, str) else json.dumps(doc), kind))
        conn.commit()
    return root


def test_validate_target_reasons(tmp_path):
    """validate_target gives exactly one reason per way a target is not evaluable, and never raises."""
    import pytest

    turn = {"turn": 1, "role": "tpm", "delivered": True, "body": "Ship it."}
    legacy_turn = {k: v for k, v in turn.items() if k != "body"}  # run-2's shape
    delivered = {"delivered": True, "verdict": "Defer."}
    runs = ["ok", "bare", "silent", "flip", "junk", "legacy", "legacy-kept", "linked", "threadless"]
    home = _mini_home(
        tmp_path / "home",
        [(r, "committee") for r in runs] + [("eval-1", "committee-eval")],
        [
            ("ok", "turn", turn), ("ok", "decision", delivered),
            ("eval-1", "eval", {"schema": 1}),
            ("silent", "decision", {"delivered": False, "verdict": ""}),
            ("flip", "decision", delivered), ("flip", "decision", {"delivered": False}),
            ("junk", "decision", "{not json"),
            ("legacy", "turn", legacy_turn), ("legacy", "decision", delivered),
            ("legacy-kept", "turn", legacy_turn), ("legacy-kept", "decision", delivered),
            ("linked", "turn", legacy_turn), ("linked", "decision", delivered),
            ("threadless", "turn", turn), ("threadless", "decision", delivered),
        ],
    )
    kept = home / "runs" / "legacy-kept" / "thread.md"
    kept.parent.mkdir(parents=True)
    kept.write_text("# Committee — legacy-kept\n", encoding="utf-8")
    linked = home / "runs" / "linked" / "thread.md"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(kept)  # read_regular follows no symlink: this is no thread.md
    h = str(home)

    assert (E.ENV_RUN, E.ENV_HOME) == ("HERMES_COMMITTEE_EVAL_RUN", "HERMES_COMMITTEE_EVAL_HOME")
    assert E.validate_target(h, None) == "HERMES_COMMITTEE_EVAL_RUN is not set"
    assert E.validate_target(h, "") == "HERMES_COMMITTEE_EVAL_RUN is not set"
    missing = tmp_path / "missing"
    assert E.validate_target(str(missing), "ok") == f"no queue.db in {missing}"
    not_a_file = tmp_path / "dir-db"
    (not_a_file / "queue.db").mkdir(parents=True)
    assert E.validate_target(str(not_a_file), "ok") == f"no queue.db in {not_a_file}"
    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / "queue.db").write_bytes(b"this is not a database")
    assert E.validate_target(str(corrupt), "ok") == f"no queue.db in {corrupt}"
    for bad in ("../ok", "run 9", ".hidden", "-x", "ok\n", "ok/x", "café"):
        assert E.validate_target(h, bad) == f"bad run id: {bad}"
    assert E.validate_target(h, "run-404") == "run not found: run-404"
    assert E.validate_target(h, "eval-1") == "not a committee run: eval-1 (committee-eval)"
    for run_id in ("bare", "silent", "flip", "junk"):  # flip: only the latest decision is read
        assert E.validate_target(h, run_id) == f"no delivered decision: {run_id}"
    assert E.validate_target(h, "legacy") == "legacy run without thread.md"
    assert E.validate_target(h, "linked") == "legacy run without thread.md"
    assert E.validate_target(h, "legacy-kept") is None
    assert E.validate_target(h, "threadless") is None  # non-legacy: read from its reductions
    assert E.validate_target(h, "ok") is None
    assert not missing.exists()
    assert sorted(p.name for p in (home / "runs").iterdir()) == ["legacy-kept", "linked"]
    with pytest.raises(ValueError, match="^run not found: run-404$"):
        E.load_target(h, "run-404")  # the loader refuses what validation refuses


def test_answered_reviewer_turns_both_rules(tmp_path):
    """D3: answers_turn when the owner turns record it (even as null), else the order rule, never N+1."""
    import dataclasses

    home, run_id = build_home(tmp_path, "run-9")
    base = E.load_target(str(home), run_id)
    assert E.unanswered_reviewer_turns(base) == []  # run-9 predates answers_turn: order rule
    (tmp_path / "two").mkdir()
    run2 = E.load_target(*map(str, build_home(tmp_path / "two", "run-2")))
    assert E.unanswered_reviewer_turns(run2) == []  # legacy: no answers_turn, order rule

    # (turn, role, delivered, answers_turn); t14 and t15 do not exist.
    rows = [
        (1, "senior_director", True, None), (2, "owner", True, 1),
        (3, "junior_ic", True, None), (4, "manager", True, None),
        (5, "junior_ic", True, None), (6, "owner", True, None),  # follows t04, answers nobody
        (7, "tpm", True, None), (8, "pm", True, None),
        (9, "owner", False, 8),  # undelivered: answers nothing
        (10, "tl", True, None), (11, "owner", True, 7),
        (12, "staff_ic", False, None),  # undelivered reviewer turns are never counted
        (13, "data_scientist", True, None), (16, "owner", True, 13),
        (17, "senior_director", True, None),  # the last turn: nobody after it
    ]

    def target(answers: str) -> "E.Target":
        turns = {}
        for n, role, delivered, answers_turn in rows:
            doc = {"turn": n, "role": role, "delivered": delivered, "body": f"t{n}"}
            if answers == "all" or (answers == "t06" and n == 6):
                doc["answers_turn"] = answers_turn if role == "owner" else None
            turns[n] = doc
        return dataclasses.replace(base, turns=turns)

    # No answers_turn anywhere: the first later turn that is not the junior IC's decides.
    # t04 is answered by t06 across t05; t13 by t16 across the gap.
    assert E.unanswered_reviewer_turns(target("none")) == [7, 8, 17]
    # Recorded: only a delivered owner turn naming N answers N, whatever follows it.
    assert E.unanswered_reviewer_turns(target("all")) == [4, 8, 10, 17]
    # One explicit null is enough to mean recorded, and it answers nobody.
    assert E.unanswered_reviewer_turns(target("t06")) == [1, 4, 7, 8, 10, 13, 17]


RUN9_TOKENS = {"input": 402, "output": 278815, "cache_creation": 2304109, "cache_read": 13727431}


def test_tokens_dedupe_and_cost_rules(tmp_path):
    """T6: usage once per message.id per trace, the last cost-state per trace, null cost on a gap (G4)."""
    import json

    from playbooks.committee.eval import trace_totals, compute_metrics, load_target

    def jl(*objs):
        return b"".join(json.dumps(o).encode() + b"\n" for o in objs)

    def asst(mid, **usage):
        return {"type": "assistant", "message": {"id": mid, "usage": usage}}

    a = jl(
        asst("m1", input_tokens=1, output_tokens=10),
        # the same message.id again: its last line wins, the first counts nothing
        asst("m1", input_tokens=2, output_tokens=20,
             cache_creation_input_tokens=5, cache_read_input_tokens=7),
        {"type": "cost-state", "totalCostUSD": 1.0},
        asst("m2", output_tokens=3),  # missing keys count 0
        {"type": "cost-state", "totalCostUSD": 1.2345},  # the last NUMERIC one wins
        {"type": "cost-state", "totalCostUSD": "9.0"},  # a string is not a cost
        {"type": "cost-state", "totalCostUSD": True},  # nor is a bool
        [1, 2],
        {"type": "assistant", "message": "not a dict"},
        {"type": "assistant", "message": {"usage": {"output_tokens": 1000}}},  # no id: skipped
    ) + b"not json\n\xff\n"
    # m1 again in ANOTHER trace: dedupe is per trace, so it counts again
    b = jl(asst("m1", output_tokens=100), {"type": "cost-state", "totalCostUSD": 2})
    a_tokens = {"input": 2, "output": 23, "cache_creation": 5, "cache_read": 7}

    assert trace_totals([a, b]) == {
        "cost_usd": 3.2345,
        "tokens": {"input": 2, "output": 123, "cache_creation": 5, "cache_read": 7},
        "found": 2, "with_cost": 2,
    }
    # a missing trace: cost is null, tokens are summed over what was found
    assert trace_totals([a, None]) == {
        "cost_usd": None, "tokens": a_tokens, "found": 1, "with_cost": 1}
    # a trace with no cost-state line nulls the cost too
    assert trace_totals([a, jl(asst("x", output_tokens=1))])["cost_usd"] is None
    # nothing found: tokens are null as well
    nothing = {"cost_usd": None, "tokens": None, "found": 0, "with_cost": 0}
    assert trace_totals([None, None]) == nothing
    assert trace_totals([]) == nothing

    # run-9's pins (C5): 25 attempts, 25 traces, each with a cost-state line
    home, run_id = build_home(tmp_path, "run-9")
    m = compute_metrics(load_target(str(home), run_id))
    assert m["time"] == {"summed_attempt_s": 3284.0, "wall_clock_s": 3619.0}
    assert m["cost_usd"] == 30.3875
    assert m["tokens"] == RUN9_TOKENS
    assert m["traces"] == {"expected": 25, "found": 25, "with_cost": 25}

    # one trace gone: cost null, found < expected, tokens are what the other 24 hold
    gone = sorted((home / "runs" / run_id / "traces").glob("*.jsonl"))[0]
    lost = trace_totals([gone.read_bytes()])["tokens"]
    gone.unlink()
    m = compute_metrics(load_target(str(home), run_id))
    assert m["cost_usd"] is None
    assert m["traces"] == {"expected": 25, "found": 24, "with_cost": 24}
    assert m["tokens"] == {k: RUN9_TOKENS[k] - lost[k] for k in RUN9_TOKENS}
    # time comes from the attempts rows, never from the traces
    assert m["time"] == {"summed_attempt_s": 3284.0, "wall_clock_s": 3619.0}

    # run-2 (legacy): its traces carry usage but no cost-state line (C5, spec A4)
    (tmp_path / "two").mkdir()
    home2, run2 = build_home(tmp_path / "two", "run-2")
    m = compute_metrics(load_target(str(home2), run2))
    assert m["time"] == {"summed_attempt_s": 3279.4, "wall_clock_s": 3516.0}
    assert m["cost_usd"] is None
    assert m["tokens"] == {
        "input": 214, "output": 183920, "cache_creation": 1768249, "cache_read": 6785620}
    assert m["traces"] == {"expected": 21, "found": 21, "with_cost": 0}


def test_unknown_kinds_retakes_new_seats(tmp_path):
    """T15: later loops' kinds, discarded takes, a duplicate turn and a seat the cast never had."""
    import json
    import sqlite3
    import time

    from playbooks.committee import cast
    from playbooks.committee.eval import compute_metrics, load_target

    home, run_id = build_home(tmp_path, "run-9")
    before = compute_metrics(load_target(str(home), run_id))
    assert before["turns"] == 24
    assert before["turns_by_role"] == {
        "owner": 8, "junior_ic": 8, "senior_director": 2, "manager": 1, "tpm": 1,
        "pm": 1, "tl": 1, "staff_ic": 1, "data_scientist": 1,
    }
    assert (before["undelivered_turns"], before["owner_turns_delivered"],
            before["delegations"]) == (0, 8, 8)
    assert (before["rechecks"], before["rechecks_verified"], before["errors"]) == (8, 8, 0)
    assert before["floor_requests"] == [{"turn": 1, "role": "senior_director"}]
    assert (before["ended"], before["cap"], before["artifact_intact"]) == ("queue empty", 30, True)
    assert before["dropped"] == {"delegation": None, "floor_requests": []}
    reviewers = ["senior_director", "manager", "tpm", "pm", "tl", "staff_ic", "data_scientist"]
    assert before["seats"] == {"roster": ["owner", *reviewers, "junior_ic"],
                               "reviewers": reviewers, "spoken": reviewers, "unheard": []}
    assert before["unanswered_reviewer_turns"] == []
    assert [x["line"] for x in before["outside_room_mentions"]] == [29, 37, 253, 309]
    assert before["outside_room_mentions"][0]["quote"].startswith(
        "- **Auth needs a yes from outside this room.**")
    assert (before["other_kinds"], before["extra_takes"]) == ({}, 0)

    assert "security" not in cast.CAST
    now = time.time()
    db = sqlite3.connect(home / "queue.db")
    t03 = next(doc for (doc,) in db.execute(
        "SELECT json FROM reductions WHERE run_id=? AND kind='turn' ORDER BY id", (run_id,))
        if json.loads(doc)["turn"] == 3)
    security = {"role": "security", "turn": 25, "delivered": True,
                "body": "Nobody from security has signed off on cross-node auth.",
                "stance": None, "cap": 30, "request_floor": False, "delegate": False,
                "close": False, "action": None, "verified": None, "error": None}
    rows = [
        ("take", "t02-owner", json.dumps({"turn": 2, "role": "owner", "body": "a discarded take"})),
        ("take", "t04-owner", json.dumps({"turn": 4, "role": "owner", "body": "another one"})),
        ("turn", "t03-junior_ic", t03),  # a second t03: the later wins, the earlier is extra
        ("selection", "selection", json.dumps({"roster": ["owner", "security", "junior_ic"]})),
        ("one_on_one_plan", "one_on_one_plan", json.dumps({"pairs": [["owner", "security"]]})),
        ("one_on_one", "one_on_one-security", json.dumps({"member": "security", "body": "1:1"})),
        ("turn", "t25-security", json.dumps(security)),
    ]
    db.executemany(
        "INSERT INTO reductions (run_id, kind, json, review_state, created_at, updated_at, phase)"
        " VALUES (?, ?, ?, 'pending', ?, ?, ?)",
        [(run_id, kind, doc, now, now, phase) for kind, phase, doc in rows])
    (start,) = db.execute(
        "SELECT MIN(a.started_at) FROM attempts a JOIN tickets t ON a.ticket_id=t.id"
        " WHERE t.run_id=?", (run_id,)).fetchone()
    for phase in ("selection", "one_on_one_plan", "one_on_one-security"):
        db.execute(
            "INSERT INTO tickets (id, run_id, phase, state, created_at, updated_at)"
            " VALUES (?, ?, ?, 'done', ?, ?)", (f"{run_id}/{phase}", run_id, phase, now, now))
        # 10 s each, inside the run's span, and no trace file
        db.execute(
            "INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at, outcome)"
            " VALUES (?, ?, 'localhost', 1, ?, ?, 'ok')",
            (f"{run_id}/{phase}", phase, start + 100.0, start + 110.0))
    db.commit()
    db.close()

    m = compute_metrics(load_target(str(home), run_id))  # never raises
    assert m["extra_takes"] == 3  # two takes plus the losing t03
    assert m["other_kinds"] == {"selection": 1, "one_on_one_plan": 1, "one_on_one": 1}
    assert m["turns"] == 25
    assert m["turns_by_role"] == {**before["turns_by_role"], "security": 1}
    assert m["seats"] == {
        "roster": ["owner", *reviewers, "junior_ic", "security"],
        "reviewers": [*reviewers, "security"],
        "spoken": [*reviewers, "security"], "unheard": [],
    }
    assert m["unanswered_reviewer_turns"] == [25]  # nobody answered the new seat
    # one attempt per new phase counts in time and in the expected traces
    assert m["time"] == {"summed_attempt_s": 3314.0, "wall_clock_s": 3619.0}
    assert m["traces"] == {"expected": 28, "found": 25, "with_cost": 25}
    assert m["cost_usd"] is None  # three attempts have no trace
    assert m["tokens"] == RUN9_TOKENS
    for key in ("owner_turns_delivered", "delegations", "rechecks", "rechecks_verified",
                "floor_requests", "ended", "cap", "outside_room_mentions"):
        assert m[key] == before[key], key
