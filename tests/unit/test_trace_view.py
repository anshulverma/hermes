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


# --- what only looks like a prompt ---------------------------------------

def test_a_slash_command_is_the_prompt_unwrapped_from_its_tags():
    """Hermes dispatches `/goal <condition>`. The transcript records the whole
    XML-ish wrapper; the reader wants the instruction and the command name."""
    raw = _lines({
        "type": "user", "timestamp": "2026-08-05T09:00:00Z",
        "message": {"role": "user", "content": (
            "<command-name>/goal</command-name>\n"
            "<command-message>goal</command-message>\n"
            "<command-args>Write one report over 17 items</command-args>"
        )},
    })

    out = trace_view.normalize(raw)

    assert len(out["records"]) == 1
    rec = out["records"][0]
    assert rec["kind"] == "prompt"
    assert rec["title"] == "/goal"
    assert rec["text"] == "Write one report over 17 items"


def test_a_command_with_no_args_keeps_its_whole_text():
    out = trace_view.normalize(_lines({
        "type": "user",
        "message": {"role": "user", "content": "<command-name>/clear</command-name>"},
    }))

    rec = out["records"][0]
    assert rec["kind"] == "prompt"
    assert rec["title"] == "/clear"
    assert "command-name" in rec["text"]


def test_the_commands_own_stdout_is_not_a_second_prompt():
    """`/goal` echoes what it set; the transcript files that echo as a user turn,
    so it reads as the operator prompting twice."""
    out = trace_view.normalize(_lines({
        "type": "user",
        "message": {"role": "user", "content": "<local-command-stdout>Goal set: do the thing</local-command-stdout>"},
    }))

    rec = out["records"][0]
    assert rec["kind"] == "command_output"
    assert "Goal set: do the thing" in rec["text"]


def test_a_hook_injection_is_not_a_prompt():
    """isMeta marks text the harness injected, not something a human typed."""
    out = trace_view.normalize(_lines({
        "type": "user", "isMeta": True,
        "message": {"role": "user", "content": "A session-scoped Stop hook is now active"},
    }))

    assert out["records"][0]["kind"] == "meta"


def test_a_real_prompt_is_still_a_prompt():
    out = trace_view.normalize(_lines({
        "type": "user",
        "message": {"role": "user", "content": "just fix the flaky test"},
    }))

    assert out["records"][0]["kind"] == "prompt"
    assert out["records"][0]["title"] == ""


def test_the_three_shapes_together_leave_exactly_one_prompt():
    """The case that made a real trace read as three prompts back to back."""
    out = trace_view.normalize(_lines(
        {"type": "user", "message": {"role": "user", "content":
            "<command-name>/goal</command-name>\n<command-args>do it</command-args>"}},
        {"type": "user", "message": {"role": "user", "content":
            "<local-command-stdout>Goal set: do it</local-command-stdout>"}},
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": "hook active"}},
    ))

    assert out["counts"]["prompt"] == 1
    assert out["counts"]["command_output"] == 1
    assert out["counts"]["meta"] == 1


# --- a trace that is not JSONL at all ------------------------------------

def test_a_whole_file_json_document_is_one_record_not_one_per_line():
    """Not every agent writes JSONL. One private adapter's trace is a single
    pretty-printed JSON document; read line-by-line, a 2.5 MB file became
    440,648 unparsed records -- enough to hang the window that renders them."""
    doc = json.dumps({"session_id": "s1", "traces": [{"a": 1}, {"b": 2}]}, indent=2)

    out = trace_view.normalize(doc)

    assert len(out["records"]) == 1
    assert out["records"][0]["kind"] == "document"
    assert out["unparsed"] == 0
    assert "session_id" in out["records"][0]["text"]


def test_a_single_line_jsonl_record_is_still_a_record():
    """A one-record JSONL file also parses as a whole; it must not be reclassified."""
    out = trace_view.normalize(_lines({"type": "user", "message": {"role": "user", "content": "hi"}}))

    assert out["records"][0]["kind"] == "prompt"


def test_real_jsonl_is_never_taken_for_a_document():
    out = trace_view.normalize(_lines(
        {"type": "user", "message": {"role": "user", "content": "a"}},
        {"type": "user", "message": {"role": "user", "content": "b"}},
    ))

    assert [r["kind"] for r in out["records"]] == ["prompt", "prompt"]


def test_a_json_document_that_is_a_list_is_also_one_record():
    out = trace_view.normalize(json.dumps([{"a": 1}, {"b": 2}], indent=2))

    assert len(out["records"]) == 1
    assert out["records"][0]["kind"] == "document"


# --- a second agent's rollout format -------------------------------------

def _codex(ptype, **payload):
    return {"timestamp": "2026-08-04T22:49:41Z", "type": "response_item",
            "payload": {"type": ptype, **payload}}


def test_a_rollout_message_from_the_assistant_is_an_answer():
    out = trace_view.normalize(_lines(_codex(
        "message", role="assistant", content=[{"type": "output_text", "text": "done"}],
    )))

    rec = out["records"][0]
    assert rec["kind"] == "answer"
    assert rec["text"] == "done"


def test_a_rollout_message_from_the_operator_is_a_prompt():
    out = trace_view.normalize(_lines(_codex(
        "message", role="user", content=[{"type": "input_text", "text": "review it"}],
    )))

    assert out["records"][0]["kind"] == "prompt"
    assert out["records"][0]["text"] == "review it"


def test_rollout_reasoning_is_thinking():
    out = trace_view.normalize(_lines(_codex("reasoning", summary=[{"text": "planning"}])))

    assert out["records"][0]["kind"] == "thinking"


def test_rollout_tool_calls_and_their_output():
    out = trace_view.normalize(_lines(
        _codex("function_call", name="spawn_agent", arguments='{"x":1}'),
        _codex("custom_tool_call", name="shell", input="ls"),
        _codex("function_call_output", call_id="c1", output="ok"),
        _codex("custom_tool_call_output", call_id="c2", output=[{"text": "listing"}]),
    ))

    assert [r["kind"] for r in out["records"]] == [
        "tool_call", "tool_call", "tool_result", "tool_result",
    ]
    assert out["records"][0]["title"] == "spawn_agent"


def test_rollout_bookkeeping_is_meta():
    out = trace_view.normalize(_lines(
        {"type": "event_msg", "payload": {"type": "token_count", "info": {}}},
        {"type": "session_meta", "payload": {"id": "x"}},
        {"type": "turn_context", "payload": {}},
    ))

    assert all(r["kind"] == "meta" for r in out["records"])


def test_an_unrecognised_rollout_payload_is_kept_as_meta():
    out = trace_view.normalize(_lines(_codex("something_new", data=1)))

    rec = out["records"][0]
    assert rec["kind"] == "meta"
    assert "something_new" in rec["text"]
