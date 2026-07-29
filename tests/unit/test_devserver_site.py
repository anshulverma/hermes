"""Tests for sites.devserver.DevserverSite.

TDD: written first (Slice 0).
"""


def test_packages_importable():
    """Smoke test: sites.devserver package can be imported."""
    import sites.devserver  # noqa: F401

    # Successfully imported if we reach here
    assert True
