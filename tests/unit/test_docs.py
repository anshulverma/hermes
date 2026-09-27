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


def test_committee_spec_documents_selection():
    """docs/specs/committee-playbook.md states how a run seats its committee and the contract later loops use."""
    import re

    from playbooks.committee import cast, selection, thread
    from playbooks.committee import eval as committee_eval

    root = Path(__file__).parent.parent.parent
    content = (root / "docs" / "specs" / "committee-playbook.md").read_text()
    # every number the spec gives a module constant is the module's, wherever it is repeated
    assert set(re.findall(r"`selection\.FIELD_MAX` = (\d+)", content)) == {str(selection.FIELD_MAX)}
    assert len(re.findall(r"`selection\.FIELD_MAX` = \d+", content)) >= 2
    # the SPA's empty-state gate, read from the view itself rather than restated
    view = (root / "playbooks" / "committee" / "view" / "src" / "CommitteeView.tsx").read_text()
    [gate] = re.findall(r"if \((data\.timeline\.length === 0 && \(+data\.selection[^{]*?)\) \{", view)

    for needle in (
        "## Selection", "s1-owner", "s2-manager-take2", "s3-senior_director",
        "cast.LIBRARY", "partner_owner", "cast.DERIVED_STYLE",
        f"`selection.FIELD_MAX` = {selection.FIELD_MAX}",
        f"`selection.NAME_MAX` = {selection.NAME_MAX}",
        f"`selection.TITLE_MAX` = {selection.TITLE_MAX}",
        f"`selection.RATIONALE_MAX` = {selection.RATIONALE_MAX}",
        f"`selection.CONSIDERED_MAX` ({selection.CONSIDERED_MAX})",
        f"`selection.INVALID_MAX` ({selection.INVALID_MAX})",
        f"`thread.LIST_MAX` ({thread.LIST_MAX})",
        f"`cast.SPEAKS_FOR_MAX` ({cast.SPEAKS_FOR_MAX})",
        f"over the {selection.MAX_REVIEWERS}-seat bound", gate,
        "```hermes-selection", "chair_failed", "invalid: name taken",
        "_apply_selection(s, resolved)", "2 × reviewers + 16",
        "- Reviewer seats: chosen below", "Seat library:",
        "## selection N: Name, Title (role) proposes|amends|ratifies",
        "_(no usable seat list:", "## committee seated",
        "Put forward by <Name>. | A fixed seat. | In the default committee.",
        "Everyone considered was seated.", "Not represented.", "Represented by <Name> (<slug>).",
        "{seated, reviewers, considered, considered_dropped, invalid_dropped, fallback}",
        "not_seated_dropped, invalid_count", "{state, current, stages, fallback, considered",
        "_(the seat list was the whole answer)_", "The chair's retake.", "You also speak for:",
        "Why you hold this seat", 's["considered"]', "selection.fallback_words(code)",
        cast.DERIVED_STYLE, committee_eval.DIMENSIONS["concern_coverage"], "SELECTION_PHASES", "<slug> · derived seat",
        "lower `selection.FIELD_MAX`, never raise `GOAL_MAX`",
        's["roster"]', 's["reviewers"]', 's["cap_explicit"]', 's["current_kind"]',
        's["base"]', 's["selection_next"]',
        '`None`, `"select"`, `"turn"` or `"decision"`', 'Junior turns are `"turn"`',
        "test_the_manager_is_the_owners_manager",
    ):
        assert needle in content, f"committee spec does not document {needle!r}"
    for stale in (
        "is not configurable",
        "| `HERMES_COMMITTEE_MAX_TURNS` | `30` |",
        "the opening round in seniority order",
    ):
        assert stale not in content, f"committee spec still says {stale!r}"
