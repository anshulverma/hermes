"""Tests for sites.local.site.LocalSite.

TDD: written first.
"""
import socket
import subprocess

import pytest

from testkit import fixtures


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def local_site():
    import sites.local  # noqa: F401  (registers "local")
    from engine import site

    return site.load("local")


def test_name_and_flags(local_site):
    assert local_site.name == "local"
    assert local_site.resource_classes() == ["cpu"]
    assert local_site.guarantees_no_ship() is True


def test_discover_hosts_returns_local_host(local_site):
    hosts = local_site.discover_hosts()
    assert hosts == [socket.gethostname()]


def test_run_worker_is_deferred(local_site):
    from testkit.mock_agent import MockAgent

    with pytest.raises(NotImplementedError, match="Slice 7"):
        local_site.run_worker("localhost", {}, MockAgent())


def test_health_reports_each_failing_check_and_merges_agent(home, local_site):
    """health before provision -> workspace check fails; agent checks merged."""
    from testkit.mock_agent import MockAgent

    host = socket.gethostname()
    report = local_site.health(host, MockAgent())

    # Site checks present
    names = {c.name for c in report.checks}
    assert "transport" in names
    assert "workspace" in names
    assert "guard" in names
    # Agent checks merged in
    assert "agent" in names
    assert "auth" in names

    # workspace not provisioned -> that check fails, reported individually
    workspace_check = next(c for c in report.checks if c.name == "workspace")
    assert workspace_check.ok is False
    assert report.workspace_ready is False
    # Overall ok reflects the failing check
    assert report.ok is False

    # resources reflect cpu count
    assert report.resources == {"cpu": __import__("os").cpu_count()}


def test_health_fails_when_agent_unhealthy(home, local_site):
    from testkit.mock_agent import MockAgent

    host = socket.gethostname()
    # Provision first so the workspace check passes, isolating the agent failure
    _make_git_repo_and_provision(home, host)

    report = local_site.health(host, MockAgent(healthy=False))
    assert report.ok is False
    assert report.agent_ok is False


def test_health_all_pass_after_provision(home, local_site):
    from testkit.mock_agent import MockAgent

    host = socket.gethostname()
    _make_git_repo_and_provision(home, host)

    report = local_site.health(host, MockAgent())
    assert report.workspace_ready is True
    assert report.ok is True


def test_health_reachable_true_for_localhost_variants(home, local_site):
    """health sets reachable=True for localhost variants."""
    from testkit.mock_agent import MockAgent

    for host in [socket.gethostname(), "localhost", "127.0.0.1"]:
        report = local_site.health(host, MockAgent())
        assert report.reachable is True, f"Expected {host} to be reachable"
        # transport check should pass
        transport_check = next(c for c in report.checks if c.name == "transport")
        assert transport_check.ok is True


def test_issue_source_reads_canned_file(home, local_site):
    from engine.models import IssueQuery

    issues_dir = home / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    fixtures.write_canned_issues(issues_dir / "bug.json")

    issues = local_site.issue_source(IssueQuery(kind="bug"))
    assert len(issues) == len(fixtures.CANNED_ISSUES)
    for iss in issues:
        assert iss.kind == "bug"  # kind echoes the query
        assert iss.id
        assert iss.ref


def test_issue_source_respects_limit(home, local_site):
    from engine.models import IssueQuery

    issues_dir = home / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    fixtures.write_canned_issues(issues_dir / "bug.json")

    issues = local_site.issue_source(IssueQuery(kind="bug", limit=1))
    assert len(issues) == 1


def test_submit_for_review_returns_file_ref_and_never_pushes(home, local_site, monkeypatch):
    host = socket.gethostname()
    repo = _make_git_repo_and_provision(home, host)

    # Guard: fail loudly if anything tries to push
    real_run = subprocess.run

    def guard(cmd, *a, **k):
        if isinstance(cmd, (list, tuple)) and "push" in cmd:
            raise AssertionError(f"submit_for_review must never push: {cmd}")
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", guard)

    ref = local_site.submit_for_review(host, {"branch": "hermes-review/t-0", "title": "x"})
    assert ref.startswith("file://")


# --- helpers -------------------------------------------------------------

def _make_git_repo_and_provision(home, host):
    """Create a source git repo, point HERMES_REPO at it, and provision."""
    import os
    from engine import site

    repo = home / "src"
    repo.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "README").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, env=env)
    os.environ["HERMES_REPO"] = str(repo)

    st = site.load("local")
    st.provision(host, "HEAD")
    return repo
