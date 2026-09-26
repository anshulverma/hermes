#!/usr/bin/env python3
"""Backfill doc/ snapshots for one committee run reduced before they existed.

    python scripts/backfill_doc_snapshots.py --run run-9 --rev 2b23385 \
        --path docs/specs/federation-future.md [--dry-run]

Run it from the repo root: the original is ``git show <rev>:<path>``. Each
junior-IC turn's recorded Edit calls are replayed from its traces onto that
original, and ``runs/<run>/doc/00-original<ext>`` and ``doc/tNN<ext>`` are
written under HERMES_HOME -- the names a new run writes -- or nothing is: every
check runs before the first write, and any mismatch aborts. queue.db is opened
read-only, so no database row changes.

Stdlib-only.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import config  # noqa: E402
from playbooks.committee import cast, thread  # noqa: E402
from playbooks.committee.replay import ReplayError, apply_edits, edit_calls  # noqa: E402


def open_db(home: Path) -> sqlite3.Connection:
    """``home/queue.db``, read-only: any write through it raises."""
    return sqlite3.connect(f"file:{home}/queue.db?mode=ro", uri=True)


def changed(before: bytes, after: bytes) -> tuple[int, int]:
    """(removed, added) lines. The two file headers are skipped by position,
    because a removed body line can itself start with ``--``."""
    diff = list(difflib.unified_diff(
        before.decode("utf-8", errors="replace").splitlines(),
        after.decode("utf-8", errors="replace").splitlines(),
        n=0, lineterm="",
    ))[2:]
    return (sum(line.startswith("-") for line in diff),
            sum(line.startswith("+") for line in diff))


def backfill(run: str, rev: str, path: str, *, dry_run: bool) -> None:
    """Every check, then (unless ``dry_run``) one rename onto ``runs/<run>/doc``.

    Raises:
        ReplayError: a check failed; nothing was written.
    """
    home = config.resolve_home()
    conn = open_db(home)
    try:
        docs = [json.loads(raw) for (raw,) in conn.execute(
            "SELECT json FROM reductions WHERE run_id=? AND kind='turn' ORDER BY id", (run,)
        )]
        if not docs:
            raise ReplayError(f"{run} has no turn reductions")
        artifact, revised = docs[-1].get("artifact"), docs[-1].get("revised")
        if not (isinstance(artifact, str) and artifact and isinstance(revised, str) and revised):
            raise ReplayError(f"{run}'s latest turn records no artifact and revised path")
        if Path(path).name != Path(artifact).name:
            raise ReplayError(f"--path {path} is not the reviewed {Path(artifact).name}")
        # The last reduction per turn wins, as in the view.
        juniors = {
            doc["turn"]: doc for doc in docs
            if doc.get("role") == cast.JUNIOR and isinstance(doc.get("turn"), int)
        }
        # By ticket, never by position: attempts of other phases interleave.
        attempts = {
            turn: [row[0] for row in conn.execute(
                "SELECT id FROM attempts WHERE ticket_id=? ORDER BY id",
                (f"{run}/t{turn:02d}-{cast.JUNIOR}",),
            )]
            for turn in juniors
        }
    finally:
        conn.close()

    data = subprocess.run(
        ["git", "show", f"{rev}:{path}"], capture_output=True, check=True
    ).stdout
    runs = home / "runs" / run
    versions = [(thread.snapshot_key(artifact, None), data)]
    for turn in sorted(juniors):
        if not attempts[turn]:
            raise ReplayError(f"t{turn:02d} has no attempts")
        before = data
        for attempt in attempts[turn]:
            trace = runs / "traces" / f"{attempt}.jsonl"
            if not trace.is_file():
                raise ReplayError(f"t{turn:02d}: no trace for attempt {attempt} at {trace}")
            data = apply_edits(data, edit_calls(trace, revised))
        verified = juniors[turn].get("verified")
        if verified is True and data == before:
            raise ReplayError(f"t{turn:02d} was verified but its edits changed nothing")
        if verified is False and data != before:
            raise ReplayError(f"t{turn:02d} did not apply but its edits changed the document")
        versions.append((thread.snapshot_key(artifact, turn), data))

    final = runs / "revised" / Path(artifact).name
    if not final.is_file() or final.read_bytes() != data:
        raise ReplayError(f"the replay does not reproduce {final} byte for byte")
    if (runs / "doc").exists():
        raise ReplayError(f"{runs / 'doc'} already exists")

    for (_, before), (key, after) in zip(versions, versions[1:]):
        removed, added = changed(before, after)
        print(f"{Path(key).stem} -{removed}/+{added}")
    print(f"final sha256 {hashlib.sha256(data).hexdigest()}")
    if dry_run:
        return

    temp = runs / ".doc-tmp"
    temp.mkdir(mode=0o700)
    try:
        for key, blob in versions:
            fd = os.open(temp / Path(key).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with open(fd, "wb") as handle:
                handle.write(blob)
        os.rename(temp, runs / "doc")
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill doc/ snapshots for one run.")
    parser.add_argument("--run", required=True)
    parser.add_argument("--rev", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        backfill(args.run, args.rev, args.path, dry_run=args.dry_run)
    except (ReplayError, OSError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        print(f"backfill: aborted, nothing written: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
