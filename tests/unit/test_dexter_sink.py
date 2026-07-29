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
