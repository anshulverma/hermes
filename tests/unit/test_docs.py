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


def test_committee_spec_documents_the_doc_snapshots_and_the_stepper():
    """docs/specs/committee-playbook.md says where each version lands and how the tab shows it."""
    spec_path = Path(__file__).parent.parent.parent / "docs" / "specs" / "committee-playbook.md"
    content = spec_path.read_text()

    for needle in (
        "runs/<run_id>/doc/", "00-original<ext>", "tNN<ext>",
        "answers_turn", "delegated_by_turn", "dropped_delegation_turn",
        "scripts/backfill_doc_snapshots.py",
        "Original · Edit 1 (tNN) … · Final",
        "view/artifact?path=doc/<name>",
    ):
        assert needle in content, f"committee spec does not document {needle!r}"
    assert "which=" not in content, "committee spec still documents the removed which= parameter"


def test_committee_eval_spec_documents_the_cli_and_the_rubric():
    """docs/specs/committee-eval.md tells the next loops how to score a run and which names they build on."""
    from playbooks.committee import eval as committee_eval

    specs = Path(__file__).parent.parent.parent / "docs" / "specs"
    content = (specs / "committee-eval.md").read_text()

    for needle in (
        "python -m playbooks.committee.eval_cli run",
        "python -m playbooks.committee.eval_cli compare",
        "evals.jsonl",
        "HERMES_COMMITTEE_EVAL_RUN",
        "HERMES_COMMITTEE_EVAL_HOME",
        "verdict_grounded", "edits_address_concerns", "concern_coverage",
        "efficiency", "concision", "verdict_consistency",
    ):
        assert needle in content, f"committee-eval spec does not document {needle!r}"
    # The names later loops build on must be real, and spelled in the doc as the code spells them.
    for name in ("words", "DIMENSIONS", "dimension_versions", "rubric_version", "compute_metrics", "calibration"):
        assert hasattr(committee_eval, name), f"playbooks/committee/eval.py has no {name}"
        assert f"`{name}" in content, f"committee-eval spec does not name `{name}`"
    assert "](committee-eval.md)" in (specs / "committee-playbook.md").read_text(), \
        "committee-playbook.md does not link committee-eval.md"


def test_committee_spec_documents_voice_and_retakes():
    """docs/specs/committee-playbook.md states the rules, the retake contract and the headroom."""
    spec_path = Path(__file__).parent.parent.parent / "docs" / "specs" / "committee-playbook.md"
    content = spec_path.read_text()

    for needle in (
        "## Voice and retakes", "Ground rules for every speaker:", "playbooks/committee/voice.py",
        "{base}-take{k}", "DECISION_PHASES", "_begin(s, base)", "file_images=False",
        "_discard(", "kind=\"take\"", "retake_failed", "chair retake failed",
        "runs/<run_id>/images/", "view/artifact?path=images/<name>",
        "action: <one sentence, 200 characters or fewer>", "stance: <20 words or fewer>",
        "<run>/decision-take{k}", "Goal headroom",
    ):
        assert needle in content, f"committee spec is missing {needle!r}"
