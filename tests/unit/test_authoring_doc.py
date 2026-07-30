"""Static test guarding the playbook authoring guide against drift.

Asserts docs/AUTHORING-PLAYBOOKS.md exists and names the real discovery env var
and the real run command, so the guide can't silently diverge from the engine's
dynamic-discovery mechanism (engine/config.py, engine/cli.py).
"""
from pathlib import Path


def _doc_text() -> str:
    doc = Path(__file__).parent.parent.parent / "docs" / "AUTHORING-PLAYBOOKS.md"
    assert doc.exists(), "docs/AUTHORING-PLAYBOOKS.md does not exist"
    return doc.read_text()


def test_authoring_doc_exists():
    _doc_text()


def test_authoring_doc_mentions_discovery_env_var():
    """Guide must name the real HERMES_PLAYBOOK_MODULES discovery var."""
    assert "HERMES_PLAYBOOK_MODULES" in _doc_text()


def test_authoring_doc_mentions_run_command():
    """Guide must show the real `hermes run` command."""
    assert "hermes run" in _doc_text()
