"""Static documentation tests (Slice 10 operability).

Assert README and RUNBOOK contain expected content.
"""
from pathlib import Path


def test_readme_no_longer_in_design_phase():
    """README must not say 'Design phase' anymore (built features landed)."""
    readme_path = Path(__file__).parent.parent.parent / "README.md"
    content = readme_path.read_text()

    assert "Design phase" not in content, "README still says 'Design phase' (wrong; engine core + dexter + sites + control-plane all built)"


def test_readme_contains_quickstart():
    """README must contain quickstart commands."""
    readme_path = Path(__file__).parent.parent.parent / "README.md"
    content = readme_path.read_text()

    # Check for all required quickstart commands
    assert "pip install -e '.[dev,server]'" in content, "README missing quickstart: pip install"
    assert "hermes run example" in content, "README missing quickstart: hermes run example"
    assert "hermes serve --api" in content, "README missing quickstart: hermes serve --api"
    assert "hermes doctor" in content, "README missing quickstart: hermes doctor"


def test_runbook_exists():
    """docs/RUNBOOK.md must exist."""
    runbook_path = Path(__file__).parent.parent.parent / "docs" / "RUNBOOK.md"
    assert runbook_path.exists(), "docs/RUNBOOK.md does not exist"


def test_runbook_covers_all_lifecycle_areas():
    """RUNBOOK must cover deploy/topology/shutdown/backup-restore/prune/token-rotation/doctor."""
    runbook_path = Path(__file__).parent.parent.parent / "docs" / "RUNBOOK.md"
    content = runbook_path.read_text().lower()

    # Required section topics (case-insensitive search)
    required_topics = [
        "deploy",          # Deploy/upgrade
        "topology",        # Run topology
        "shutdown",        # Graceful shutdown/restart
        "backup",          # Backup/restore
        "prune",           # Prune/vacuum
        "token",           # Token rotation
        "doctor",          # Doctor diagnostics
    ]

    for topic in required_topics:
        assert topic in content, f"RUNBOOK missing coverage of: {topic}"


def test_runbook_db_flags_match_cli():
    """RUNBOOK db command examples must use real argparse flags (guard against drift)."""
    runbook_path = Path(__file__).parent.parent.parent / "docs" / "RUNBOOK.md"
    content = runbook_path.read_text()

    # Assert the correct flags are present
    assert "--events-older-than" in content, "RUNBOOK missing --events-older-than flag"
    assert "--attempts-older-than" in content, "RUNBOOK missing --attempts-older-than flag"
    assert "--out" in content, "RUNBOOK missing --out flag for backup"

    # Assert the wrong flags are NOT present (guard against stale/incorrect flags)
    assert "--events-days" not in content, "RUNBOOK has stale flag --events-days (should be --events-older-than)"
    assert "--attempts-days" not in content, "RUNBOOK has stale flag --attempts-days (should be --attempts-older-than)"
    assert "db backup --output" not in content, "RUNBOOK has wrong flag --output (should be --out)"
