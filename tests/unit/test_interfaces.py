"""Tests for the Playbook / Site / Agent Protocols, their registries, and
HealthReport.ok.

TDD: written first. These pin the §8 interface surface every later slice
depends on.
"""
import pytest


# --- HealthReport.ok (models change) -------------------------------------

def test_health_report_ok_true_iff_all_checks_pass():
    """HealthReport.ok is True iff every Check passed."""
    from engine.models import HealthReport, Check

    def make(checks):
        return HealthReport(
            reachable=True,
            agent_ok=True,
            auth_ok=True,
            workspace_ready=True,
            guard_installed=True,
            resources={"cpu": 4},
            latency_ms=1,
            checks=checks,
        )

    assert make([Check("a", True, ""), Check("b", True, "")]).ok is True
    assert make([Check("a", True, ""), Check("b", False, "boom")]).ok is False
    # No checks -> vacuously ok
    assert make([]).ok is True


# --- Registries ----------------------------------------------------------

def test_playbook_registry_register_and_load():
    from engine import playbook

    sentinel = object()
    playbook.register("__test_pb__", sentinel)
    assert playbook.load("__test_pb__") is sentinel


def test_site_registry_register_and_load():
    from engine import site

    sentinel = object()
    site.register("__test_site__", sentinel)
    assert site.load("__test_site__") is sentinel


def test_agent_registry_register_and_load():
    from engine import agent

    sentinel = object()
    agent.register("__test_agent__", sentinel)
    assert agent.load("__test_agent__") is sentinel


def test_unknown_name_raises_clear_error():
    from engine import playbook, site, agent

    with pytest.raises(Exception) as e:
        playbook.load("nope-playbook")
    assert "nope-playbook" in str(e.value)

    with pytest.raises(Exception) as e:
        site.load("nope-site")
    assert "nope-site" in str(e.value)

    with pytest.raises(Exception) as e:
        agent.load("nope-agent")
    assert "nope-agent" in str(e.value)


# --- Concrete implementations resolve by name ----------------------------

def test_concrete_registrations_resolve():
    """Importing the concrete modules registers example/local/mock."""
    import testkit  # noqa: F401  (registers example + mock)
    import sites.local  # noqa: F401  (registers local)
    from engine import playbook, site, agent

    pb = playbook.load("example")
    st = site.load("local")
    ag = agent.load("mock")

    assert pb.name == "example"
    assert st.name == "local"
    assert ag.name == "mock"


# --- Protocol conformance (runtime_checkable) ----------------------------

def test_concrete_objects_satisfy_protocols():
    import testkit  # noqa: F401
    import sites.local  # noqa: F401
    from engine import playbook, site, agent
    from engine.playbook import Playbook
    from engine.site import Site
    from engine.agent import Agent

    assert isinstance(playbook.load("example"), Playbook)
    assert isinstance(site.load("local"), Site)
    assert isinstance(agent.load("mock"), Agent)
