"""Tests for playbooks.dexter.DexterPlaybook.

TDD: written first (Slice 0).
"""


def test_packages_importable():
    """Smoke test: playbooks and playbooks.dexter packages can be imported."""
    import playbooks  # noqa: F401
    import playbooks.dexter  # noqa: F401

    # Successfully imported if we reach here
    assert True
