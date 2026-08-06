"""Tests for engine.trace: capturing a worker's own trace at result time.

TDD: written FIRST, watched fail, then engine/trace.py implemented.

The engine stays generic here. It knows only two optional questions: "agent,
where is your trace?" (``agent.trace_source``) and "site, fetch me that file"
(``site.fetch_file``). Neither is required, and every failure is swallowed —
capture is evidence-gathering, never a reason for a dispatch to fail.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine import trace
from engine.models import Result


def _result(ref="claude:session:abc"):
    return Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref=ref,
        error_summary=None,
        started_at=1.0,
        ended_at=2.0,
        payload={"answer": "done"},
        evidence_ref=None,
    )


class _Agent:
    """An agent that can name its trace."""

    def __init__(self, source="~/traces/*.jsonl"):
        self._source = source
        self.asked_with = None

    def trace_source(self, result, envelope):
        self.asked_with = (result, envelope)
        return self._source


class _MuteAgent:
    """An agent with no trace_source at all (the pre-existing shape)."""


class _Site:
    """A site that can fetch a file, writing fixed content."""

    def __init__(self, content=b'{"type":"user"}\n', ok=True):
        self._content = content
        self._ok = ok
        self.calls = []

    def fetch_file(self, host, source, dest):
        self.calls.append((host, source, str(dest)))
        if not self._ok:
            return False
        Path(dest).write_bytes(self._content)
        return True


class _MuteSite:
    """A site with no fetch_file (the pre-existing shape)."""


class _AngrySite:
    """A site whose fetch blows up."""

    def fetch_file(self, host, source, dest):
        raise OSError("host went away mid-copy")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def _capture(site, agent, **kw):
    return trace.capture(
        site=site, host="h1", agent=agent, result=kw.pop("result", _result()),
        envelope=kw.pop("envelope", {"ticket_id": "run-1/t-0"}),
        run_id=kw.pop("run_id", "run-1"), attempt_id=kw.pop("attempt_id", 7), **kw
    )


# --- the happy path ------------------------------------------------------

def test_capture_writes_trace_under_the_run_directory(home):
    path = _capture(_Site(), _Agent())

    assert path is not None
    assert path == home / "runs" / "run-1" / "traces" / "7.jsonl"
    assert path.read_bytes() == b'{"type":"user"}\n'


def test_capture_asks_the_agent_with_the_result_and_envelope(home):
    agent = _Agent()
    result = _result()
    envelope = {"ticket_id": "run-1/t-0"}

    _capture(_Site(), agent, result=result, envelope=envelope)

    assert agent.asked_with == (result, envelope)


def test_capture_passes_the_agents_source_through_to_the_site(home):
    site = _Site()

    _capture(site, _Agent("~/.claude/projects/*/abc.jsonl"))

    assert len(site.calls) == 1
    host, source, _dest = site.calls[0]
    assert host == "h1"
    assert source == "~/.claude/projects/*/abc.jsonl"


def test_trace_path_is_derived_from_run_and_attempt(home):
    assert trace.trace_path("run-9", 42) == home / "runs" / "run-9" / "traces" / "42.jsonl"


def test_capture_is_owner_only(home):
    path = _capture(_Site(), _Agent())

    assert oct(path.stat().st_mode)[-3:] == "600"


# --- the ways it declines, all of them quiet -----------------------------

def test_agent_without_trace_source_captures_nothing(home):
    assert _capture(_Site(), _MuteAgent()) is None


def test_agent_that_names_no_source_captures_nothing(home):
    site = _Site()

    assert _capture(site, _Agent(None)) is None
    assert site.calls == []


def test_empty_source_is_not_a_source(home):
    assert _capture(_Site(), _Agent("   ")) is None


def test_site_without_fetch_file_captures_nothing(home):
    assert _capture(_MuteSite(), _Agent()) is None


def test_failed_fetch_captures_nothing_and_leaves_no_file(home):
    path = _capture(_Site(ok=False), _Agent())

    assert path is None
    assert not (home / "runs" / "run-1" / "traces" / "7.jsonl").exists()


def test_a_site_that_raises_never_reaches_the_caller(home):
    assert _capture(_AngrySite(), _Agent()) is None


def test_an_agent_that_raises_never_reaches_the_caller(home):
    class Exploding:
        def trace_source(self, result, envelope):
            raise RuntimeError("bad ref")

    assert _capture(_Site(), Exploding()) is None


def test_a_fetch_reporting_success_without_writing_captures_nothing(home):
    class Liar:
        def fetch_file(self, host, source, dest):
            return True  # says yes, writes nothing

    assert _capture(Liar(), _Agent()) is None


# --- the size cap --------------------------------------------------------

def test_a_trace_over_the_cap_is_discarded_not_kept_half(home, monkeypatch):
    monkeypatch.setenv("HERMES_TRACE_MAX_MB", "1")
    big = b"x" * (2 * 1024 * 1024)

    path = _capture(_Site(content=big), _Agent())

    assert path is None
    assert not (home / "runs" / "run-1" / "traces" / "7.jsonl").exists()


def test_a_trace_inside_the_cap_is_kept(home, monkeypatch):
    monkeypatch.setenv("HERMES_TRACE_MAX_MB", "1")

    path = _capture(_Site(content=b"y" * 1024), _Agent())

    assert path is not None


def test_max_bytes_defaults_when_unset(home, monkeypatch):
    monkeypatch.delenv("HERMES_TRACE_MAX_MB", raising=False)

    assert trace.max_bytes() == trace.DEFAULT_MAX_MB * 1024 * 1024


def test_max_bytes_ignores_a_nonsense_setting(home, monkeypatch):
    monkeypatch.setenv("HERMES_TRACE_MAX_MB", "not-a-number")

    assert trace.max_bytes() == trace.DEFAULT_MAX_MB * 1024 * 1024


# --- reading it back -----------------------------------------------------

def test_read_returns_none_when_no_trace_was_captured(home):
    assert trace.read("run-1", 7) is None


def test_read_returns_what_capture_wrote(home):
    _capture(_Site(content=b'{"type":"assistant"}\n'), _Agent())

    assert trace.read("run-1", 7) == '{"type":"assistant"}\n'


def test_read_refuses_an_attempt_id_that_is_not_a_number(home):
    """The attempt id reaches this from a URL path; it must not walk the tree."""
    with pytest.raises(ValueError):
        trace.trace_path("run-1", "../../../etc/passwd")


def test_read_refuses_a_run_id_that_climbs(home):
    with pytest.raises(ValueError):
        trace.trace_path("../../etc", 1)


def test_size_reports_bytes_on_disk(home):
    _capture(_Site(content=b"z" * 400), _Agent())

    assert trace.size("run-1", 7) == 400
    assert trace.size("run-1", 999) is None


def test_capture_overwrites_a_stale_trace_for_the_same_attempt(home):
    _capture(_Site(content=b"first\n"), _Agent())
    _capture(_Site(content=b"second\n"), _Agent())

    assert trace.read("run-1", 7) == "second\n"


def test_capture_tolerates_a_home_it_cannot_write(home, monkeypatch):
    """A home that cannot hold a runs/ directory loses the trace, not the run."""
    blocker = home / "blocker"
    blocker.write_text("I am a file, not a directory")
    monkeypatch.setenv("HERMES_HOME", str(blocker / "home"))

    assert _capture(_Site(), _Agent()) is None


def test_read_of_undecodable_bytes_does_not_raise(home):
    _capture(_Site(content=b"\xff\xfe not utf-8 \xff"), _Agent())

    out = trace.read("run-1", 7)
    assert isinstance(out, str)
