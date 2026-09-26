"""The committee eval's command line: ``python -m playbooks.committee.eval_cli <cmd>``.

- ``run <run> [--home H] [--agent A]`` scores one finished committee run.
- ``show <run> [--home H]`` prints that run's eval.json as a table.
- ``compare [--rubric R ...]`` prints one row per evaluated run, from the ledger.
- ``anchor <run> [--home H] <id>=<1-5>... [--rater R] [--note T]`` records the
  user's own scores, which calibrate the judge.

It is not in engine/cli.py, for two reasons: the guard test forbids naming the
committee there, and ``hermes run`` exits 0 whatever state its run ends in
(spec D9). The package ``__init__`` never imports this module.
``python -m playbooks.committee.eval`` hands off to ``main`` here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from engine import cli as engine_cli
from playbooks.committee import eval as ev
from playbooks.committee import thread

MODULES = "HERMES_PLAYBOOK_MODULES"
PACKAGE = "playbooks.committee"
NULL = "—"
QUOTE_COLS = 80
STALE_NOTE = "* older definition; re-run `eval run <target>`"


def _fail(message: str) -> int:
    """Print a rejection to stderr, and exit 2."""
    print(message, file=sys.stderr)
    return 2


def _home(arg: str | None) -> str:
    """The source home: --home's realpath, else the eval home (spec D2)."""
    return os.path.realpath(arg) if arg else ev.eval_home()


def _ledger() -> list[dict] | None:
    """Every parseable line of the eval home's ledger: [] when it has none, None when unreadable."""
    return ev.read_ledger(ev.ledger_path(ev.eval_home()))


def _score(value: object) -> str:
    return NULL if value is None else str(value)


def _quote(dim: dict) -> str:
    """The dimension's first verified evidence quote, or ""."""
    return next((e.get("quote") or "" for e in dim.get("evidence") or []
                 if isinstance(e, dict) and e.get("verified") is True), "")


def _key(line: dict) -> tuple:
    """A ledger line's target key: (home realpath, run, created_at)."""
    target = line.get("target") or {}
    return (target.get("home"), target.get("run"), target.get("created_at"))


def _table(rows: list[list[str]]) -> str:
    """Rows as ``a | b | c`` lines, each column padded to its widest cell."""
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join(" | ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip()
                     for row in rows)


def _run(run: str, home: str, agent: str | None) -> int:
    """Validate the target, drive one committee-eval run to its end, then show it.

    Exits 2 on a bad target, having created nothing, and 0 only when the eval
    run ended ``done``.
    """
    reason = ev.validate_target(home, run)
    if reason:
        return _fail(reason)
    os.environ[ev.ENV_RUN] = run
    os.environ[ev.ENV_HOME] = home
    modules = [m.strip() for m in os.environ.get(MODULES, "").split(",") if m.strip()]
    if PACKAGE not in modules:
        os.environ[MODULES] = ",".join([*modules, PACKAGE])
    started = time.time()
    engine_cli.main(["run", "committee-eval", "--site", "local", "--wait",
                     *(["--agent", agent] if agent else [])])
    row = None
    conn = ev.connect_ro(ev.eval_home())
    if conn is not None:
        try:
            row = conn.execute(
                "SELECT id, state FROM runs WHERE playbook = 'committee-eval'"
                " AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
                (started,),
            ).fetchone()
        finally:
            conn.close()
    if row is None:
        print("no committee-eval run was started", file=sys.stderr)
        return 1
    print(f"eval run {row[0]}: {row[1]}")
    _show(run, home)
    return 0 if row[1] == "done" else 1


def _show(run: str, home: str) -> int:
    """Print the target's eval.json as a table. Exits 1 when there is none."""
    path = ev.eval_json_path(ev.eval_home(), home, run)
    data = thread.read_regular(path)
    if data is None:
        print(f"no eval.json for {run}", file=sys.stderr)
        return 1
    try:
        body = json.loads(data)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        print(f"unreadable eval.json for {run}: {path}", file=sys.stderr)
        return 1
    ledger = _ledger()
    labels = ev.calibration(ledger) if ledger is not None else {}
    unlabelled = "uncalibrated" if ledger is not None else "unknown"  # an unreadable ledger
    rubric = body.get("rubric") or {}
    dims = body.get("dimensions") or {}
    rows = [["dimension", "score", "scorer", "calibration", "quote"]]
    for d in ev.DIMENSIONS:
        dim = dims.get(d) or {}
        judged = d in ev.JUDGE_DIMS
        rows.append([d, _score(dim.get("score")), "judge" if judged else "deterministic",
                     labels.get(rubric.get(d), unlabelled) if judged else "",
                     _quote(dim)[:QUOTE_COLS]])
    print(_table(rows))
    flags = [f"{f.get('id')}@t{f['turn']:02d}" if isinstance(f.get("turn"), int) else str(f.get("id"))
             for f in body.get("flags") or [] if isinstance(f, dict)]
    print("flags: " + (", ".join(flags) or "none"))
    print(f"headline: {body.get('headline', '')}")
    judge = body.get("judge") or {}
    error = f" ({judge['error']})" if judge.get("error") else ""
    print(f"judge: {judge.get('status')}{error}")
    return 0


def _compare(rubrics: list[str] | None) -> int:
    """One row per evaluated target: its latest eval line, whatever its rubric.

    ``--rubric`` filters the evaluations only. Anchors always count, so a
    filtered table still shows the user's scores and their calibration.
    """
    ledger = _ledger()
    if ledger is None:
        print(f"cannot read {ev.ledger_path(ev.eval_home())}", file=sys.stderr)
        return 1
    kept = [line for line in ledger
            if line.get("source") != "eval" or not rubrics
            or line.get("rubric_version") in rubrics]
    latest = ev.latest_evals([line for line in kept if line.get("source") == "eval"])
    if not latest:
        print(f"no evaluations in {ev.ledger_path(ev.eval_home())}")
        return 0
    anchored: dict[tuple, dict] = {}  # (target key, dimension) -> {version: score}
    for line in kept:
        if line.get("source") == "anchor":
            for d, cell in (line.get("dimensions") or {}).items():
                anchored.setdefault((_key(line), d), {})[cell.get("version")] = cell.get("score")
    current = ev.dimension_versions()
    home = ev.eval_home()
    rows, stale = [], False
    for line in latest.values():
        key = _key(line)
        where = Path(key[0])
        row = [key[1] if key[0] == home else f"{where.parent.name}/{where.name}:{key[1]}"]
        for d in ev.DIMENSIONS:
            cell = (line.get("dimensions") or {}).get(d) or {}
            version, text = cell.get("version"), _score(cell.get("score"))
            if version != current[d]:
                text, stale = text + "*", True
            marks = anchored.get((key, d), {}) if d in ev.JUDGE_DIMS else {}
            if version in marks:
                text += f" (a:{marks[version]})"
            elif marks and current[d] not in marks:
                text += " (re-score needed)"
            row.append(text)
        rows.append(row)
    labels = ev.calibration(kept)
    calibration = [labels.get(current[d], "uncalibrated") if d in ev.JUDGE_DIMS else ""
                   for d in ev.DIMENSIONS]
    print(_table([["target", *ev.DIMENSIONS], *sorted(rows), ["calibration", *calibration]]))
    if stale:
        print(STALE_NOTE)
    return 0


def _anchor(run: str, home: str, pairs: list[str], rater: str | None, note: str | None) -> int:
    """Append one anchor line for the target, carrying the current dimension versions."""
    scores: dict[str, int] = {}
    for pair in pairs:
        dim, _, value = pair.partition("=")
        if dim not in ev.DIMENSIONS:
            return _fail(f"unknown dimension: {dim} (known: {', '.join(ev.DIMENSIONS)})")
        if value not in ("1", "2", "3", "4", "5"):
            return _fail(f"{dim} must be an integer from 1 to 5, not {value!r}")
        scores[dim] = int(value)
    if not scores:
        return _fail("no scores given: anchor <run> <id>=<1-5>...")
    reason = ev.validate_target(home, run)
    if reason:
        return _fail(reason)
    conn = ev.connect_ro(home)
    try:
        created_at = conn.execute("SELECT created_at FROM runs WHERE id = ?", (run,)).fetchone()[0]
    finally:
        conn.close()
    target = {"home": home, "run": run, "created_at": created_at}
    try:
        ev.append_ledger(ev.eval_home(),
                         ev.anchor_line(target, scores, ev.dimension_versions(), rater, note))
    except OSError as exc:  # a symlinked ledger or a short write: main returns, never raises
        print(f"cannot append to {ev.ledger_path(ev.eval_home())}: {exc}", file=sys.stderr)
        return 1
    print(f"anchored {run}: " + ", ".join(f"{d}={s}" for d, s in scores.items()))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv`` (default ``sys.argv[1:]``) and run one command; returns the exit code."""
    parser = argparse.ArgumentParser(prog="python -m playbooks.committee.eval_cli",
                                     description="Score finished committee runs.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cmd = sub.add_parser("run", help="score one finished committee run")
    cmd.add_argument("run")
    cmd.add_argument("--home", help="the run's HERMES_HOME, read only (default: this one)")
    cmd.add_argument("--agent", help="the judge's agent (default: HERMES_AGENT)")
    cmd = sub.add_parser("show", help="print a run's evaluation as a table")
    cmd.add_argument("run")
    cmd.add_argument("--home", help="the run's HERMES_HOME (default: this one)")
    cmd = sub.add_parser("compare", help="one row per evaluated run, from evals.jsonl")
    cmd.add_argument("--rubric", nargs="+", help="keep only evaluations at these rubric_versions")
    cmd = sub.add_parser("anchor", help="record your own scores for a run")
    cmd.add_argument("run")
    cmd.add_argument("scores", nargs="*", metavar="id=score", help="e.g. verdict_grounded=3")
    cmd.add_argument("--home", help="the run's HERMES_HOME, read only (default: this one)")
    cmd.add_argument("--rater")
    cmd.add_argument("--note")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # a usage error exits 2 (--help 0); main returns, never raises
        return exc.code if isinstance(exc.code, int) else 2
    if args.cmd == "run":
        return _run(args.run, _home(args.home), args.agent)
    if args.cmd == "show":
        return _show(args.run, _home(args.home))
    if args.cmd == "compare":
        return _compare(args.rubric)
    return _anchor(args.run, _home(args.home), args.scores, args.rater, args.note)


if __name__ == "__main__":
    sys.exit(main())
