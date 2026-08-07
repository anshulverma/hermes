"""Read a captured worker trace into something a person can follow.

A trace as captured (``engine.trace``) is one JSON object per line, and most of
those lines are not the conversation. In a real 150-line session: 82 hook
attachments, 17 bookkeeping records, and 51 lines of actual work. Dumped
verbatim into a window, the session is there but unreadable -- which is the same
place you were in with a path on the clipboard.

So each line is flattened into the blocks a reader cares about -- a prompt, an
answer, a thought, a tool call, its result -- and everything else is *classified*
rather than dropped. Nothing is discarded: an unrecognized record type still
comes through as ``meta`` carrying its own JSON, and a line that will not parse
comes through as ``unparsed`` carrying the line. A reader who wants the bytes
exactly as captured asks for the raw form instead.

This is deliberately format-led, not agent-led: it recognizes the record shapes
a JSONL transcript uses and degrades to ``meta`` for anything it has not seen
before, so a new agent tool's trace is readable-ish on day one and never blank.

Stdlib-only.
"""
from __future__ import annotations

import json
import re
from typing import Any

# The wrappers a transcript uses around a dispatched slash command and its own
# echoed output. Both arrive as user turns; only the first is a prompt.
_COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.S)
_COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_STDOUT_RE = re.compile(r"<local-command-stdout>(.*?)</local-command-stdout>", re.S)

# Content blocks that carry the session, mapped to the kind a reader sees.
_BLOCK_KINDS = {
    "text": "answer",
    "thinking": "thinking",
    "redacted_thinking": "thinking",
    "tool_use": "tool_call",
    "tool_result": "tool_result",
}

# Record types that are session bookkeeping rather than conversation.
_META_TYPES = {"last-prompt", "queue-operation", "summary", "system"}


def normalize(raw: str) -> dict[str, Any]:
    """Flatten a JSONL trace into ordered, classified records.

    Returns a dict of ``records`` (each with ``line``, ``kind``, ``role``,
    ``ts``, ``title``, ``text``), plus ``counts`` per kind and the ``lines`` /
    ``bytes`` / ``unparsed`` totals describing the source.
    """
    records: list[dict[str, Any]] = []
    lines = 0
    unparsed = 0

    for index, line in enumerate((raw or "").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        lines += 1
        try:
            doc = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            doc = None
        if not isinstance(doc, dict):
            unparsed += 1
            records.append(_record(index, "unparsed", None, None, "unparsed line", stripped))
            continue
        records.extend(_records_for(index, doc))

    counts: dict[str, int] = {}
    for rec in records:
        counts[rec["kind"]] = counts.get(rec["kind"], 0) + 1

    return {
        "records": records,
        "counts": counts,
        "lines": lines,
        "bytes": len((raw or "").encode("utf-8")),
        "unparsed": unparsed,
    }


def _records_for(index: int, doc: dict) -> list[dict[str, Any]]:
    """The reader-facing records for one source line."""
    rtype = doc.get("type")
    ts = doc.get("timestamp") if isinstance(doc.get("timestamp"), str) else None

    if rtype == "attachment":
        att = doc.get("attachment")
        att = att if isinstance(att, dict) else {}
        title = str(att.get("type") or "attachment")
        return [_record(index, "attachment", None, ts, title, _dump(att))]

    if rtype in ("user", "assistant"):
        message = doc.get("message")
        message = message if isinstance(message, dict) else {}
        role = message.get("role") if isinstance(message.get("role"), str) else rtype
        content = message.get("content")

        if isinstance(content, str):
            if role == "user":
                return [_user_text(index, role, ts, content, is_meta=doc.get("isMeta") is True)]
            return [_record(index, "answer", role, ts, "", content)]

        if isinstance(content, list):
            out = [r for r in (_block(index, role, ts, b) for b in content) if r]
            # A turn whose blocks are all unrecognized still has to show up.
            return out or [_record(index, "meta", role, ts, str(rtype), _dump(doc))]

        # Neither shape: keep the line rather than lose the turn.
        kind = "prompt" if role == "user" else "answer"
        return [_record(index, kind, role, ts, "", _dump(content))]

    if rtype in _META_TYPES or rtype is None:
        return [_record(index, "meta", None, ts, str(rtype or "record"), _dump(doc))]

    # An unrecognized type is still evidence: keep it whole.
    return [_record(index, "meta", None, ts, str(rtype), _dump(doc))]


def _user_text(index: int, role, ts, content: str, *, is_meta: bool) -> dict[str, Any]:
    """Classify a user-role string, which is often not a prompt at all.

    Three things arrive as user turns and only the first is one:

    * the slash command that was dispatched -- the real instruction, wrapped in
      ``<command-name>`` / ``<command-args>`` tags. Unwrapped here, so the reader
      sees the goal and the command that carried it rather than the markup.
    * that command's own stdout, echoed back. It restates the instruction, which
      is why a trace reads as the operator prompting twice in a row.
    * text the harness injected (hook notes, reminders), marked ``isMeta``.
    """
    if is_meta:
        return _record(index, "meta", role, ts, "injected", content)

    stdout = _STDOUT_RE.search(content)
    if stdout:
        return _record(index, "command_output", role, ts, "command output", stdout.group(1).strip())

    name = _COMMAND_NAME_RE.search(content)
    if name:
        args = _COMMAND_ARGS_RE.search(content)
        # Only substitute the args when there are some; a bare command carries
        # its meaning in the tags, and dropping them would leave an empty record.
        body = args.group(1).strip() if args and args.group(1).strip() else content
        return _record(index, "prompt", role, ts, name.group(1).strip(), body)

    return _record(index, "prompt", role, ts, "", content)


def _block(index: int, role, ts, block) -> dict[str, Any] | None:
    """One content block as a record, or None if it carries nothing."""
    if not isinstance(block, dict):
        return _record(index, "meta", role, ts, "block", _dump(block))

    btype = block.get("type")
    kind = _BLOCK_KINDS.get(btype)
    if kind is None:
        return _record(index, "meta", role, ts, str(btype or "block"), _dump(block))

    if kind == "answer":
        return _record(index, kind, role, ts, "", _text(block.get("text")))
    if kind == "thinking":
        return _record(index, kind, role, ts, "",
                       _text(block.get("thinking") or block.get("data")))
    if kind == "tool_call":
        name = str(block.get("name") or "tool")
        return _record(index, kind, role, ts, name, _dump(block.get("input")))
    # tool_result
    return _record(index, kind, role, ts, str(block.get("tool_use_id") or ""),
                   _text(block.get("content")))


def _record(line: int, kind: str, role, ts, title: str, text: str) -> dict[str, Any]:
    return {
        "line": line,
        "kind": kind,
        "role": role,
        "ts": ts,
        "title": title,
        "text": text if isinstance(text, str) else _dump(text),
    }


def _text(value) -> str:
    """A content value as text, whatever shape it arrived in."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(_dump(item))
        return "\n".join(parts)
    return _dump(value)


def _dump(value) -> str:
    """Readable JSON for anything that is not already text."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)
