"""Tests for server.trace_view: turning a captured JSONL trace into something readable.

TDD: written FIRST, watched fail, then server/trace_view.py implemented.

A captured trace is one JSON object per line, and most of those lines are not
conversation: in a real 150-line trace, 82 were hook attachments and 17 were
bookkeeping. The reader's job is to surface the 51 that are the actual session
and classify the rest honestly rather than dropping them.
"""
from __future__ import annotations

import json

from server import trace_view


def _lines(*objs) -> str:
    return "".join(json.dumps(o) + "\n" for o in objs)


def _assistant(*blocks):
    return {"type": "assistant", "timestamp": "2026-08-05T10:00:00Z",
            "message": {"role": "assistant", "content": list(blocks)}}


# --- the conversation ----------------------------------------------------

def test_a_user_prompt_becomes_a_prompt_record():
    raw = _lines({"type": "user", "timestamp": "2026-08-05T09:59:00Z",
                  "message": {"role": "user", "content": "review D123"}})

    out = trace_view.normalize(raw)

    assert len(out["records"]) == 1
    rec = out["records"][0]
    assert rec["kind"] == "prompt"
    assert rec["role"] == "user"
    assert rec["text"] == "review D123"
    assert rec["ts"] == "2026-08-05T09:59:00Z"


def test_assistant_text_becomes_an_answer_record():
    out = trace_view.normalize(_lines(_assistant({"type": "text", "text": "here is what I found"})))

    rec = out["records"][0]
    assert rec["kind"] == "answer"
    assert rec["role"] == "assistant"
    assert rec["text"] == "here is what I found"


def test_thinking_is_kept_but_marked_as_thinking():
    out = trace_view.normalize(_lines(_assistant({"type": "thinking", "thinking": "hmm"})))

    assert out["records"][0]["kind"] == "thinking"
    assert out["records"][0]["text"] == "hmm"


def test_a_tool_call_carries_its_name_and_input():
    out = trace_view.normalize(_lines(_assistant(
        {"type": "tool_use", "name": "Bash", "id": "t1", "input": {"command": "ls -la"}}
    )))

    rec = out["records"][0]
    assert rec["kind"] == "tool_call"
    assert rec["title"] == "Bash"
    assert "ls -la" in rec["text"]


def test_a_tool_result_is_its_own_record():
    out = trace_view.normalize(_lines({
        "type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "file1\nfile2"}
        ]},
    }))

    rec = out["records"][0]
    assert rec["kind"] == "tool_result"
    assert "file1" in rec["text"]


def test_one_line_with_several_blocks_becomes_several_records():
    """A single assistant turn is thinking + text + three tool calls; reading it
    as one blob is exactly what makes a raw trace unreadable."""
    out = trace_view.normalize(_lines(_assistant(
        {"type": "thinking", "thinking": "plan"},
        {"type": "text", "text": "doing it"},
        {"type": "tool_use", "name": "Read", "input": {"file_path": "/a"}},
    )))

    assert [r["kind"] for r in out["records"]] == ["thinking", "answer", "tool_call"]


def test_records_are_indexed_by_source_line():
    out = trace_view.normalize(_lines(
        {"type": "user", "message": {"role": "user", "content": "one"}},
        _assistant({"type": "text", "text": "two"}, {"type": "text", "text": "three"}),
    ))

    assert [r["line"] for r in out["records"]] == [0, 1, 1]


# --- the noise, classified rather than dropped ---------------------------

def test_a_hook_attachment_is_kept_as_an_attachment():
    out = trace_view.normalize(_lines({
        "type": "attachment", "timestamp": "2026-08-05T10:00:01Z",
        "attachment": {"type": "hook_success", "hookName": "PostToolUse",
                       "stdout": "ok", "exitCode": 0},
    }))

    rec = out["records"][0]
    assert rec["kind"] == "attachment"
    assert rec["title"] == "hook_success"


def test_bookkeeping_records_are_marked_meta():
    out = trace_view.normalize(_lines(
        {"type": "last-prompt", "leafUuid": "x", "sessionId": "s"},
        {"type": "queue-operation", "operation": "enqueue", "content": "c"},
    ))

    assert [r["kind"] for r in out["records"]] == ["meta", "meta"]


def test_an_unknown_record_type_is_kept_verbatim_not_dropped():
    out = trace_view.normalize(_lines({"type": "something-new-in-2027", "payload": {"a": 1}}))

    rec = out["records"][0]
    assert rec["kind"] == "meta"
    assert rec["title"] == "something-new-in-2027"
    assert "something-new-in-2027" in rec["text"]


def test_counts_summarize_what_is_in_the_trace():
    out = trace_view.normalize(_lines(
        {"type": "user", "message": {"role": "user", "content": "go"}},
        _assistant({"type": "text", "text": "ok"}),
        {"type": "attachment", "attachment": {"type": "hook_success"}},
        {"type": "attachment", "attachment": {"type": "hook_success"}},
    ))

    assert out["counts"]["prompt"] == 1
    assert out["counts"]["answer"] == 1
    assert out["counts"]["attachment"] == 2


# --- damaged input -------------------------------------------------------

def test_an_unparseable_line_is_reported_not_swallowed():
    out = trace_view.normalize('{"type":"user","message":{"role":"user","content":"a"}}\nnot json\n')

    assert out["unparsed"] == 1
    assert len(out["records"]) == 2
    assert out["records"][1]["kind"] == "unparsed"
    assert out["records"][1]["text"] == "not json"


def test_blank_lines_are_not_records():
    out = trace_view.normalize('\n\n{"type":"user","message":{"role":"user","content":"a"}}\n\n')

    assert len(out["records"]) == 1
    assert out["unparsed"] == 0


def test_an_empty_trace_is_an_empty_reading():
    out = trace_view.normalize("")

    assert out["records"] == []
    assert out["lines"] == 0


def test_a_json_line_that_is_not_an_object_is_unparsed():
    out = trace_view.normalize("[1,2,3]\n")

    assert out["records"][0]["kind"] == "unparsed"


def test_content_that_is_neither_string_nor_list_does_not_raise():
    out = trace_view.normalize(_lines({"type": "user", "message": {"role": "user", "content": 42}}))

    assert len(out["records"]) == 1
    assert out["records"][0]["kind"] in ("prompt", "meta")


def test_a_block_without_its_expected_field_does_not_raise():
    out = trace_view.normalize(_lines(_assistant(
        {"type": "text"}, {"type": "tool_use"}, {"type": "thinking"}, "not-a-dict",
    )))

    assert len(out["records"]) >= 3
    assert all(isinstance(r["text"], str) for r in out["records"])


def test_lines_and_bytes_describe_the_source():
    raw = _lines({"type": "user", "message": {"role": "user", "content": "a"}},
                 {"type": "user", "message": {"role": "user", "content": "b"}})

    out = trace_view.normalize(raw)

    assert out["lines"] == 2
    assert out["bytes"] == len(raw.encode("utf-8"))
