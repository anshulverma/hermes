"""Replay a junior IC's recorded Edit calls onto a document, in memory.

A committee run reduced before doc/ snapshots existed kept only its final
revised copy, but its junior-IC workers' traces still hold every Edit they
made. Applying each turn's edits, in order, to the original rebuilds every
intermediate version exactly. ``scripts/backfill_doc_snapshots.py`` writes them
out for one run; an eval can rebuild them in memory for a run nobody
backfilled. Pure: reads a trace, writes nothing.

Stdlib-only.
"""
from __future__ import annotations

import json
from pathlib import Path

# Tools that change a file in a way `apply_edits` cannot reproduce.
_UNREPLAYABLE = ("Write", "MultiEdit", "NotebookEdit")


class ReplayError(Exception):
    """The recorded edits cannot be replayed faithfully onto the document."""


def _blocks(trace: Path):
    """Every content block of every message in a Claude Code JSONL trace."""
    with open(trace, encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            message = record.get("message") if isinstance(record, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            for block in content if isinstance(content, list) else ():
                if isinstance(block, dict):
                    yield block


def edit_calls(trace: Path, target: str) -> list[dict]:
    """The successful ``Edit`` tool calls on ``target``, in the order they ran.

    ``target`` is the path the worker was told to edit: the reduction's
    recorded ``revised``. Calls are deduped by tool_use id, since a trace can
    repeat a message, and a call whose ``tool_result`` has ``is_error`` changed
    nothing and is dropped.

    Raises:
        ReplayError: a ``Write``, ``MultiEdit`` or ``NotebookEdit`` names
            ``target``, by ``file_path`` or by ``notebook_path``.
    """
    calls: dict[str, dict] = {}
    failed: set[str] = set()
    for block in _blocks(trace):
        if block.get("type") == "tool_use":
            args = block.get("input") if isinstance(block.get("input"), dict) else {}
            named = target in (args.get("file_path"), args.get("notebook_path"))
            if named and block.get("name") in _UNREPLAYABLE:
                raise ReplayError(f"{block['name']} on {target} cannot be replayed")
            if block.get("name") == "Edit" and args.get("file_path") == target:
                calls.setdefault(block.get("id"), block)
        elif block.get("type") == "tool_result" and block.get("is_error") is True:
            failed.add(block.get("tool_use_id"))
    return [call for call_id, call in calls.items() if call_id not in failed]


def apply_edits(data: bytes, calls: list[dict]) -> bytes:
    """``data`` with each call's ``old_string`` replaced by its ``new_string``.

    The Edit tool's own rule: exactly one occurrence, or with ``replace_all``
    every occurrence and at least one. Anything else means the replay has
    diverged from the file the worker saw.

    Raises:
        ReplayError: an ``old_string`` is empty, absent or ambiguous.
    """
    for call in calls:
        args = call.get("input") or {}
        old = str(args.get("old_string") or "").encode("utf-8")
        new = str(args.get("new_string") or "").encode("utf-8")
        count = data.count(old) if old else 0
        if args.get("replace_all") is True:
            if count < 1:
                raise ReplayError(f"replace_all found no {old[:60]!r}")
            data = data.replace(old, new)
        elif count != 1:
            raise ReplayError(f"expected exactly one {old[:60]!r}, found {count}")
        else:
            data = data.replace(old, new, 1)
    return data
