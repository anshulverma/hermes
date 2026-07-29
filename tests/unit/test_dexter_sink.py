"""Tests for playbooks.dexter.sink — LearningSink protocol + implementations.

TDD: written first (Slice 4).
"""
import pytest


def test_fake_sink_returns_canned_ref():
    """FakeSink.bank() returns the canned ref and records the call."""
    from playbooks.dexter.sink import FakeSink

    sink = FakeSink(ref="kb/test-learning-001")

    cluster = {"signature": "TEST-SIG", "canonical_ticket_id": "run-1/solve-0"}
    ref = sink.bank(cluster)

    assert ref == "kb/test-learning-001"
    assert len(sink.banked_clusters) == 1
    assert sink.banked_clusters[0] == cluster


def test_fake_sink_raises_when_configured():
    """FakeSink.bank() raises when constructed with raise_on_bank."""
    from playbooks.dexter.sink import FakeSink

    exc = RuntimeError("simulated kb.py failure")
    sink = FakeSink(raise_on_bank=exc)

    cluster = {"signature": "TEST-SIG"}

    with pytest.raises(RuntimeError) as caught:
        sink.bank(cluster)

    assert caught.value is exc
    # Should still record the attempt before raising
    assert len(sink.banked_clusters) == 1


def test_fake_sink_multiple_calls():
    """FakeSink.bank() can be called multiple times (records each)."""
    from playbooks.dexter.sink import FakeSink

    sink = FakeSink(ref="kb/multi")

    c1 = {"signature": "SIG-1"}
    c2 = {"signature": "SIG-2"}

    ref1 = sink.bank(c1)
    ref2 = sink.bank(c2)

    assert ref1 == "kb/multi"
    assert ref2 == "kb/multi"
    assert len(sink.banked_clusters) == 2
    assert sink.banked_clusters == [c1, c2]


def test_dexter_kb_sink_placeholder():
    """DexterKbSink exists and conforms to LearningSink (integration test deferred)."""
    from playbooks.dexter.sink import DexterKbSink

    # Smoke test: can construct
    sink = DexterKbSink()

    # Has a bank method
    assert callable(getattr(sink, "bank", None))

    # Integration test (actually calling kb.py) is deferred (requires dexter install)
    # This test just ensures the class exists and has the right shape


def test_dexter_kb_sink_not_configured_returns_none(monkeypatch):
    """DexterKbSink.bank() with DEXTER_KB_PY/INVESTIGATIONS_DIR unset → returns None, no raise."""
    from playbooks.dexter.sink import DexterKbSink

    # Unset env vars
    monkeypatch.delenv("DEXTER_KB_PY", raising=False)
    monkeypatch.delenv("INVESTIGATIONS_DIR", raising=False)

    sink = DexterKbSink()
    cluster = {"signature": "TEST-SIG", "canonical_ticket_id": "r/solve-0"}

    # Should return None (not configured), not raise
    ref = sink.bank(cluster)
    assert ref is None


def test_dexter_kb_sink_kb_py_unset_returns_none(monkeypatch):
    """DexterKbSink.bank() with DEXTER_KB_PY unset (INVESTIGATIONS_DIR set) → returns None."""
    from playbooks.dexter.sink import DexterKbSink

    monkeypatch.delenv("DEXTER_KB_PY", raising=False)
    monkeypatch.setenv("INVESTIGATIONS_DIR", "/fake/dir")

    sink = DexterKbSink()
    cluster = {"signature": "TEST-SIG"}

    ref = sink.bank(cluster)
    assert ref is None


def test_dexter_kb_sink_investigations_dir_unset_returns_none(monkeypatch):
    """DexterKbSink.bank() with INVESTIGATIONS_DIR unset (DEXTER_KB_PY set) → returns None."""
    from playbooks.dexter.sink import DexterKbSink

    monkeypatch.setenv("DEXTER_KB_PY", "/fake/kb.py")
    monkeypatch.delenv("INVESTIGATIONS_DIR", raising=False)

    sink = DexterKbSink()
    cluster = {"signature": "TEST-SIG"}

    ref = sink.bank(cluster)
    assert ref is None


def test_dexter_kb_sink_configured_shells_validate_then_index(tmp_path, monkeypatch):
    """DexterKbSink.bank() with config → shells kb.py validate then index, returns ref."""
    import subprocess
    from playbooks.dexter.sink import DexterKbSink

    # Create a fake kb.py that records invocations
    fake_kb_py = tmp_path / "fake_kb.py"
    invocations_file = tmp_path / "invocations.txt"

    fake_kb_py.write_text(f"""#!/usr/bin/env python3
import sys
import os

with open('{invocations_file}', 'a') as f:
    f.write(f"{{sys.argv[1]}}\\n")
    f.write(f"INVESTIGATIONS_DIR={{os.environ.get('INVESTIGATIONS_DIR', 'UNSET')}}\\n")

# Exit 0 for both validate and index
sys.exit(0)
""")
    fake_kb_py.chmod(0o755)

    inv_dir = tmp_path / "investigations"
    inv_dir.mkdir()

    monkeypatch.setenv("DEXTER_KB_PY", str(fake_kb_py))
    monkeypatch.setenv("INVESTIGATIONS_DIR", str(inv_dir))

    sink = DexterKbSink()
    cluster = {
        "signature": "TEST-SIG",
        "canonical_ticket_id": "r/solve-0",
        "cause_category": "test_cat",
        "canonical_diff_ref": "D1",
        "member_ticket_ids": ["r/solve-0"],
    }

    ref = sink.bank(cluster)

    # Should return a non-None ref
    assert ref is not None

    # Verify kb.py was called twice (validate, then index)
    invocations = invocations_file.read_text().strip().split('\n')
    # Should have: validate, INVESTIGATIONS_DIR=..., index, INVESTIGATIONS_DIR=...
    assert "validate" in invocations
    assert "index" in invocations
    assert f"INVESTIGATIONS_DIR={inv_dir}" in invocations


def test_dexter_kb_sink_validate_fails_returns_none(tmp_path, monkeypatch):
    """DexterKbSink.bank() with kb.py validate failing (exit non-zero) → returns None."""
    from playbooks.dexter.sink import DexterKbSink

    # Create a fake kb.py that exits non-zero on validate
    fake_kb_py = tmp_path / "fake_kb_fail.py"
    fake_kb_py.write_text("""#!/usr/bin/env python3
import sys
if sys.argv[1] == "validate":
    sys.exit(1)  # Fail validation
sys.exit(0)
""")
    fake_kb_py.chmod(0o755)

    inv_dir = tmp_path / "investigations"
    inv_dir.mkdir()

    monkeypatch.setenv("DEXTER_KB_PY", str(fake_kb_py))
    monkeypatch.setenv("INVESTIGATIONS_DIR", str(inv_dir))

    sink = DexterKbSink()
    cluster = {"signature": "TEST-SIG", "canonical_ticket_id": "r/solve-0"}

    # Should return None (best-effort), not raise
    ref = sink.bank(cluster)
    assert ref is None
