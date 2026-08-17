"""Tests for sites.fan.site — the per-agent fan-out site factory.

TDD: written FIRST, watched fail, then sites/fan/site.py implemented.
"""
import pytest

from engine import site as _site
from engine.models import Check, HealthReport, Issue, IssueQuery, Result
from engine.site import Site


@pytest.fixture(autouse=True)
def isolated_registries():
    """Snapshot/restore the site registry + the shared fan capacity set."""
    import sites.fan  # noqa: F401  (registers the built-in fan sites)
    from sites.fan import site as fan_site

    saved_registry = dict(_site._REGISTRY)
    saved_agents = set(fan_site._FAN_AGENTS)
    yield
    _site._REGISTRY.clear()
    _site._REGISTRY.update(saved_registry)
    fan_site._FAN_AGENTS.clear()
    fan_site._FAN_AGENTS.update(saved_agents)


class _RecordingDelegate:
    """A stand-in local site that records what was delegated to it."""

    name = "local"

    def __init__(self):
        self.calls = []

    def discover_hosts(self):
        self.calls.append(("discover_hosts",))
        return ["host-1"]

    def provision(self, host, base_ref):
        self.calls.append(("provision", host, base_ref))

    def health(self, host, agent):
        self.calls.append(("health", host))
        return HealthReport(
            reachable=True,
            agent_ok=True,
            auth_ok=True,
            workspace_ready=True,
            guard_installed=True,
            resources={"cpu": 8},
            latency_ms=3,
            checks=[Check("transport", True, "ok")],
        )

    def run_worker(self, host, envelope, agent):
        self.calls.append(("run_worker", host, envelope))
        return Result(
            outcome="ok",
            termination_reason="goal_met",
            result_ref=None,
            error_summary=None,
            started_at=0.0,
            ended_at=1.0,
        )

    def resource_classes(self):
        return ["cpu"]

    def guarantees_no_ship(self):
        self.calls.append(("guarantees_no_ship",))
        return True

    def submit_for_review(self, host, change):
        self.calls.append(("submit_for_review", host, change))
        return "file:///review"

    def issue_source(self, query):
        self.calls.append(("issue_source", query.kind))
        return [Issue(id="i1", kind=query.kind, title="t", ref="r", data={})]


def _fan_site(name="fan-x", resource_class="agent:x", delegate=None):
    from sites.fan.site import FanSite

    return FanSite(name, resource_class, delegate=delegate or _RecordingDelegate())


# --- registration --------------------------------------------------------

def test_builtin_fan_sites_resolve_by_name():
    """Importing sites.fan registers fan-claude and fan-codex."""
    import sites.fan  # noqa: F401

    assert _site.load("fan-claude").name == "fan-claude"
    assert _site.load("fan-codex").name == "fan-codex"


def test_register_fan_site_registers_a_new_site():
    import sites.fan

    sites.fan.register_fan_site("zeta")

    st = _site.load("fan-zeta")
    assert st.name == "fan-zeta"
    assert st.resource_classes() == ["agent:zeta"]


# --- routing: one class per site -----------------------------------------

def test_each_fan_site_advertises_exactly_its_own_class():
    import sites.fan  # noqa: F401

    assert _site.load("fan-claude").resource_classes() == ["agent:claude"]
    assert _site.load("fan-codex").resource_classes() == ["agent:codex"]


# --- capacity: every registered fan agent --------------------------------

def test_health_reports_capacity_for_every_registered_fan_agent():
    """The fan processes share one crew row, so capacity covers all agents."""
    import sites.fan  # noqa: F401

    delegate = _RecordingDelegate()
    st = _fan_site("fan-claude", "agent:claude", delegate=delegate)

    report = st.health("host-1", agent=object())

    assert report.resources["agent:claude"] > 0
    assert report.resources["agent:codex"] > 0
    # The delegate's own report is otherwise preserved.
    assert report.reachable is True
    assert report.guard_installed is True
    assert report.latency_ms == 3
    assert [c.name for c in report.checks] == ["transport"]


def test_registering_a_third_agent_appears_in_the_others_capacity():
    """Cross-process contract: a later registration widens everyone's capacity."""
    import sites.fan

    sites.fan.register_fan_site("zeta")

    st = _fan_site("fan-claude", "agent:claude")
    resources = st.health("host-1", agent=object()).resources

    assert resources["agent:zeta"] > 0
    assert resources["agent:claude"] > 0
    assert resources["agent:codex"] > 0
    # Routing is unchanged by the wider capacity.
    assert st.resource_classes() == ["agent:claude"]


# --- protocol conformance ------------------------------------------------

def test_fan_sites_satisfy_the_site_protocol():
    import sites.fan  # noqa: F401

    assert isinstance(_site.load("fan-claude"), Site)
    assert isinstance(_site.load("fan-codex"), Site)


def test_every_other_method_delegates():
    delegate = _RecordingDelegate()
    st = _fan_site(delegate=delegate)

    assert st.discover_hosts() == ["host-1"]
    st.provision("host-1", "main")
    assert st.run_worker("host-1", {"ticket_id": "t1"}, agent=object()).outcome == "ok"
    assert st.guarantees_no_ship() is True
    assert st.submit_for_review("host-1", {"id": "c1"}) == "file:///review"
    assert [i.id for i in st.issue_source(IssueQuery(kind="bug"))] == ["i1"]

    assert delegate.calls == [
        ("discover_hosts",),
        ("provision", "host-1", "main"),
        ("run_worker", "host-1", {"ticket_id": "t1"}),
        ("guarantees_no_ship",),
        ("submit_for_review", "host-1", {"id": "c1"}),
        ("issue_source", "bug"),
    ]


# --- lazy delegate resolution --------------------------------------------

def test_delegate_is_resolved_lazily_and_cached(monkeypatch):
    """Nothing is resolved until a delegating method is actually called."""
    from sites.fan import site as fan_site

    resolved = []
    delegate = _RecordingDelegate()

    def _fake_local_site():
        resolved.append(1)
        return delegate

    monkeypatch.setattr(fan_site, "_local_site", _fake_local_site)

    st = fan_site.FanSite("fan-x", "agent:x")
    assert resolved == []

    # Routing + naming need no delegate at all.
    assert st.name == "fan-x"
    assert st.resource_classes() == ["agent:x"]
    assert resolved == []

    assert st.discover_hosts() == ["host-1"]
    assert st.discover_hosts() == ["host-1"]
    assert resolved == [1]


def test_a_broken_delegate_does_not_break_registration(monkeypatch):
    """An unresolvable local site must not break import or routing."""
    from sites.fan import site as fan_site

    def _boom():
        raise ImportError("no local site here")

    monkeypatch.setattr(fan_site, "_local_site", _boom)

    st = fan_site.FanSite("fan-x", "agent:x")
    assert st.name == "fan-x"
    assert st.resource_classes() == ["agent:x"]
    with pytest.raises(ImportError):
        st.discover_hosts()


# --- trace capture through the fan topology ------------------------------

def test_fan_site_forwards_a_file_fetch_to_its_delegate(tmp_path):
    """Multi-agent runs execute through fan sites. A fan site that does not
    forward fetch_file captures no traces at all, and does it silently --
    engine.trace cannot tell "this site cannot fetch" from "this class forgot
    to delegate"."""
    import sites.fan  # noqa: F401
    from engine import site as _site

    src = tmp_path / "trace.jsonl"
    src.write_text('{"type":"user"}\n')
    dest = tmp_path / "out.jsonl"

    fan = _site.load("fan-claude")
    assert fan.fetch_file("localhost", str(src), dest) is True
    assert dest.read_text() == '{"type":"user"}\n'


def test_fan_site_reports_a_miss_like_any_other_site(tmp_path):
    import sites.fan  # noqa: F401
    from engine import site as _site

    fan = _site.load("fan-claude")
    assert fan.fetch_file("localhost", str(tmp_path / "nothing-here-*.jsonl"),
                          tmp_path / "out.jsonl") is False


def test_fan_site_tolerates_a_delegate_that_cannot_fetch(tmp_path):
    """fetch_file is optional on the Site protocol; a delegate without it makes
    the fan site one that cannot fetch either, not one that explodes."""
    from sites.fan.site import FanSite

    class NoFetch:
        name = "nofetch"

    fan = FanSite("fan-x", "agent:x", delegate=NoFetch())
    assert fan.fetch_file("h", "/tmp/x", tmp_path / "out") is False
