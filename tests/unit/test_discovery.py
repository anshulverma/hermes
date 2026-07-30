"""Unit tests for dynamic adapter discovery.

Tests for HERMES_PLAYBOOK_MODULES, HERMES_SITE_MODULES, HERMES_AGENT_MODULES
env vars and the dynamic import mechanism in cli.py.
"""
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
import pytest


def test_playbook_modules_accessor_parses_comma_list(monkeypatch):
    """playbook_modules() parses HERMES_PLAYBOOK_MODULES as comma-separated list."""
    from engine.config import playbook_modules

    monkeypatch.setenv('HERMES_PLAYBOOK_MODULES', 'foo.bar,baz.qux, zap.zop')
    modules = playbook_modules()
    assert modules == ['foo.bar', 'baz.qux', 'zap.zop']


def test_playbook_modules_accessor_strips_blanks(monkeypatch):
    """playbook_modules() strips leading/trailing spaces from each module path."""
    from engine.config import playbook_modules

    monkeypatch.setenv('HERMES_PLAYBOOK_MODULES', '  foo.bar  ,  baz.qux  ')
    modules = playbook_modules()
    assert modules == ['foo.bar', 'baz.qux']


def test_playbook_modules_accessor_unset_returns_empty_list(monkeypatch):
    """playbook_modules() returns [] when HERMES_PLAYBOOK_MODULES is unset."""
    from engine.config import playbook_modules

    monkeypatch.delenv('HERMES_PLAYBOOK_MODULES', raising=False)
    modules = playbook_modules()
    assert modules == []


def test_playbook_modules_accessor_empty_string_returns_empty_list(monkeypatch):
    """playbook_modules() returns [] when HERMES_PLAYBOOK_MODULES is empty string."""
    from engine.config import playbook_modules

    monkeypatch.setenv('HERMES_PLAYBOOK_MODULES', '')
    modules = playbook_modules()
    assert modules == []


def test_site_modules_accessor_parses_comma_list(monkeypatch):
    """site_modules() parses HERMES_SITE_MODULES as comma-separated list."""
    from engine.config import site_modules

    monkeypatch.setenv('HERMES_SITE_MODULES', 'foo.site,bar.site')
    modules = site_modules()
    assert modules == ['foo.site', 'bar.site']


def test_site_modules_accessor_unset_returns_empty_list(monkeypatch):
    """site_modules() returns [] when HERMES_SITE_MODULES is unset."""
    from engine.config import site_modules

    monkeypatch.delenv('HERMES_SITE_MODULES', raising=False)
    modules = site_modules()
    assert modules == []


def test_agent_modules_accessor_parses_comma_list(monkeypatch):
    """agent_modules() parses HERMES_AGENT_MODULES as comma-separated list."""
    from engine.config import agent_modules

    monkeypatch.setenv('HERMES_AGENT_MODULES', 'foo.agent,bar.agent')
    modules = agent_modules()
    assert modules == ['foo.agent', 'bar.agent']


def test_agent_modules_accessor_unset_returns_empty_list(monkeypatch):
    """agent_modules() returns [] when HERMES_AGENT_MODULES is unset."""
    from engine.config import agent_modules

    monkeypatch.delenv('HERMES_AGENT_MODULES', raising=False)
    modules = agent_modules()
    assert modules == []


def test_custom_playbook_loads_via_env_var(tmp_path, monkeypatch):
    """A custom playbook module listed in HERMES_PLAYBOOK_MODULES is imported and registers its adapter."""
    from engine import playbook
    from engine.cli import _load_playbook_site_agent

    # Create a temporary custom playbook module
    custom_module_path = tmp_path / "custom_playbook.py"
    custom_module_path.write_text("""
from engine import playbook as _playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket

class CustomPlaybook:
    name = "custom"
    phases = ["test"]

    def seed(self, run, site):
        return []

    def payload_schema(self, phase):
        return {}

    def result_schema(self, phase):
        return {}

    def driver(self, phase):
        return Driver(command=None)

    def reduce(self, run, phase, findings, site):
        return []

    def verify(self, run, ticket, result, site):
        return True

    def next_phase(self, run):
        return None

    def is_done(self, run):
        return True

# Register on import
_playbook.register("custom", CustomPlaybook())
""")

    # Add tmp_path to sys.path so the module is importable
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setenv('HERMES_PLAYBOOK_MODULES', 'custom_playbook')

    try:
        # Load should resolve the custom playbook
        args = Namespace(playbook='custom', site='local', agent='claude')
        pb, st, ag = _load_playbook_site_agent(args)

        assert pb is not None
        assert pb.name == 'custom'
    finally:
        # Cleanup
        sys.path.remove(str(tmp_path))
        # Unregister the custom playbook
        if 'custom' in playbook._REGISTRY:
            del playbook._REGISTRY['custom']
        # Remove from sys.modules if imported
        if 'custom_playbook' in sys.modules:
            del sys.modules['custom_playbook']


def test_custom_site_loads_via_env_var(tmp_path, monkeypatch):
    """A custom site module listed in HERMES_SITE_MODULES is imported and registers its adapter."""
    from engine import site
    from engine.cli import _load_playbook_site_agent

    # Create a temporary custom site module
    custom_module_path = tmp_path / "custom_site.py"
    custom_module_path.write_text("""
from engine import site as _site
from engine.models import HealthReport, Issue, IssueQuery, Result

class CustomSite:
    name = "custom_site"

    def discover_hosts(self):
        return ["custom-host"]

    def provision(self, host, base_ref):
        pass

    def health(self, host, agent):
        return HealthReport(ok=True, checks=[])

    def run_worker(self, host, envelope, agent):
        return Result(outcome="done", payload={}, result={})

    def resource_classes(self):
        return ["default"]

    def guarantees_no_ship(self):
        return True

    def submit_for_review(self, host, change):
        return "https://example.com/review/1"

    def issue_source(self, query):
        return []

# Register on import
_site.register("custom_site", CustomSite())
""")

    # Add tmp_path to sys.path
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setenv('HERMES_SITE_MODULES', 'custom_site')

    try:
        # Load should resolve the custom site
        args = Namespace(site='custom_site', agent='claude')
        pb, st, ag = _load_playbook_site_agent(args)

        assert st is not None
        assert st.name == 'custom_site'
    finally:
        # Cleanup
        sys.path.remove(str(tmp_path))
        if 'custom_site' in site._REGISTRY:
            del site._REGISTRY['custom_site']
        if 'custom_site' in sys.modules:
            del sys.modules['custom_site']


def test_custom_agent_loads_via_env_var(tmp_path, monkeypatch):
    """A custom agent module listed in HERMES_AGENT_MODULES is imported and registers its adapter."""
    from engine import agent
    from engine.cli import _load_playbook_site_agent

    # Create a temporary custom agent module
    custom_module_path = tmp_path / "custom_agent.py"
    custom_module_path.write_text("""
from engine import agent as _agent
from engine.models import Check, Driver, Result

class CustomAgent:
    name = "custom_agent"

    def build_invocation(self, envelope, driver):
        return ["echo", "custom"]

    def parse_result(self, raw, envelope):
        return Result(outcome="done", payload={}, result={})

    def health_checks(self, host, site):
        return [Check("agent", True, "custom agent ok")]

# Register on import
_agent.register("custom_agent", CustomAgent())
""")

    # Add tmp_path to sys.path
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setenv('HERMES_AGENT_MODULES', 'custom_agent')

    try:
        # Load should resolve the custom agent
        args = Namespace(site='local', agent='custom_agent')
        pb, st, ag = _load_playbook_site_agent(args)

        assert ag is not None
        assert ag.name == 'custom_agent'
    finally:
        # Cleanup
        sys.path.remove(str(tmp_path))
        if 'custom_agent' in agent._REGISTRY:
            del agent._REGISTRY['custom_agent']
        if 'custom_agent' in sys.modules:
            del sys.modules['custom_agent']


def test_bad_module_path_raises_config_error(monkeypatch):
    """A module path that doesn't import raises ConfigError naming the module."""
    from engine.config import ConfigError
    from engine.cli import _load_playbook_site_agent

    monkeypatch.setenv('HERMES_PLAYBOOK_MODULES', 'nonexistent.bad.module')

    args = Namespace(playbook='dexter', site='local', agent='claude')

    with pytest.raises(ConfigError) as exc_info:
        _load_playbook_site_agent(args)

    # Should name the module in the error
    assert 'nonexistent.bad.module' in str(exc_info.value)


def test_unset_env_preserves_existing_behavior(monkeypatch):
    """With discovery env vars unset, existing adapters still resolve (no regression)."""
    from engine.cli import _load_playbook_site_agent

    # Clear all discovery env vars
    monkeypatch.delenv('HERMES_PLAYBOOK_MODULES', raising=False)
    monkeypatch.delenv('HERMES_SITE_MODULES', raising=False)
    monkeypatch.delenv('HERMES_AGENT_MODULES', raising=False)

    # Built-in adapters should still resolve
    args = Namespace(playbook='dexter', site='local', agent='claude')
    pb, st, ag = _load_playbook_site_agent(args)

    assert pb.name == 'dexter'
    assert st.name == 'local'
    assert ag.name == 'claude'
