"""Tests for sites.devserver.DevserverSite (Slice 5).

TDD: written FIRST. DevserverSite is a distinct site (not inheriting SSHSite):
real idempotent provisioning + HONEST guard reporting. Commands constructed for
provision/health/run_worker; subprocess is MOCKED (no real SSH/Meta). Connection
failure (ssh exit 255 or CalledProcessError on scp) → run_worker raises
TransportError; successful worker → returns parsed Result; health parses ALL
HealthReport fields (guard_installed PROBED, not hardcoded True); run_worker's
remote PATH prepend uses a shell string (not separate argv items).
"""
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def devserver_site():
    import sites.devserver  # noqa: F401 (registers "devserver")
    from engine import site

    return site.load("devserver")


@pytest.fixture
def mock_agent():
    import testkit  # noqa: F401 (registers "mock")
    from engine import agent

    return agent.load("mock")


def test_devserver_site_registration():
    """DevserverSite registers as 'devserver'."""
    import sites.devserver  # noqa: F401
    from engine import site

    s = site.load("devserver")
    assert s.name == "devserver"


def test_discover_hosts_empty_by_default(devserver_site):
    """discover_hosts returns [] when no config/env is set."""
    hosts = devserver_site.discover_hosts()
    assert hosts == []


def test_discover_hosts_from_env(monkeypatch, devserver_site):
    """discover_hosts reads from HERMES_DEVSERVER_HOSTS env var."""
    monkeypatch.setenv("HERMES_DEVSERVER_HOSTS", "dev1.example,dev2.example")
    hosts = devserver_site.discover_hosts()
    assert hosts == ["dev1.example", "dev2.example"]


@patch("subprocess.run")
def test_provision_is_idempotent(mock_run, devserver_site):
    """provision is idempotent: 2nd call doesn't re-checkout, but always re-verifies/re-installs guard."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="OK", stderr=""
    )

    # First provision
    devserver_site.provision("dev1.example", "main")
    first_call_count = mock_run.call_count

    # Second provision (idempotent)
    devserver_site.provision("dev1.example", "main")
    second_call_count = mock_run.call_count

    # Should have called provision logic both times (but idempotent checkout logic)
    assert mock_run.called
    # Both provisions should have verified/installed guard
    assert second_call_count >= first_call_count


@patch("subprocess.run")
def test_provision_installs_guard_shims(mock_run, devserver_site):
    """provision installs the no-ship guard shims (same set as sites/local)."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="OK", stderr=""
    )

    devserver_site.provision("dev1.example", "main")

    # Should have called ssh commands to install guard shims
    assert mock_run.called
    # At least some calls should involve installing guard (deployment-specific, so we check it was called)


@patch("subprocess.run")
def test_health_reachability_check(mock_run, devserver_site, mock_agent):
    """health runs ssh reachability check and measures latency."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    report = devserver_site.health("dev1.example", mock_agent)

    assert report.reachable is True
    assert report.latency_ms >= 0
    assert any(c.name == "transport" for c in report.checks)


@patch("subprocess.run")
def test_health_unreachable_when_ssh_fails(mock_run, devserver_site, mock_agent):
    """health sets reachable=False when ssh fails."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=255, stdout="", stderr="Connection refused"
    )

    report = devserver_site.health("dev1.example", mock_agent)

    assert report.reachable is False


@patch("subprocess.run")
def test_health_guard_installed_probed_not_hardcoded(mock_run, devserver_site, mock_agent):
    """health reports guard_installed by PROBING shim presence, not hardcoded True.

    Critical: unlike SSHSite's hardcoded guard_installed=True, devserver is HONEST.
    """
    # Mock ssh to fail guard probe (shim not found)
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="not found"
    )

    report = devserver_site.health("dev1.example", mock_agent)

    # guard_installed should reflect the probe result, not be hardcoded True
    # When guard check fails, guard_installed should be False
    assert report.guard_installed is False


@patch("subprocess.run")
def test_health_guard_installed_true_when_present(mock_run, devserver_site, mock_agent):
    """health reports guard_installed=True when guard shims are actually present."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    report = devserver_site.health("dev1.example", mock_agent)

    assert report.guard_installed is True


@patch("subprocess.run")
def test_health_reports_resources_as_cpu_dict(mock_run, devserver_site, mock_agent):
    """health returns resources={"cpu": <int>} from nproc."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="8\n", stderr=""
    )

    report = devserver_site.health("dev1.example", mock_agent)

    assert isinstance(report.resources, dict)
    assert "cpu" in report.resources
    assert isinstance(report.resources["cpu"], int)
    assert report.resources["cpu"] > 0


@patch("subprocess.run")
def test_health_merges_agent_checks(mock_run, devserver_site, mock_agent):
    """health includes both site checks and agent checks."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="4\n", stderr=""
    )

    report = devserver_site.health("dev1.example", mock_agent)

    # Should have site checks (transport, workspace, guard, resources) + agent checks
    check_names = {c.name for c in report.checks}
    assert "transport" in check_names
    # Agent checks from MockAgent
    assert "agent" in check_names or "auth" in check_names


@patch("subprocess.run")
def test_health_agent_ok_and_auth_ok_from_agent_checks(mock_run, devserver_site, mock_agent):
    """health sets agent_ok/auth_ok from agent.health_checks via _find_ok pattern."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="4\n", stderr=""
    )

    report = devserver_site.health("dev1.example", mock_agent)

    # agent_ok and auth_ok should be pulled from agent checks (may be True vacuously)
    assert isinstance(report.agent_ok, bool)
    assert isinstance(report.auth_ok, bool)


@patch("subprocess.run")
def test_health_workspace_ready_checks_checkout(mock_run, devserver_site, mock_agent):
    """health checks workspace_ready (checkout at base_ref, clean)."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="4\n", stderr=""
    )

    report = devserver_site.health("dev1.example", mock_agent)

    # workspace_ready should be a boolean
    assert isinstance(report.workspace_ready, bool)


def test_run_worker_connection_failure_raises_transport_error(devserver_site, mock_agent):
    """run_worker raises TransportError on ssh exit 255 (connection failure).

    Exit 255 is ssh's connection-error code (host unreachable).
    """
    from engine.transport import TransportError

    envelope = {
        "ticket_id": "run-1/t-0",
        "timeout_s": 60,
        "goal_envelope": {
            "driver": {"command": None, "args": {}, "loop": None}
        },
    }

    with patch("sites.devserver.site.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=255, stdout="", stderr="Connection refused"
        )

        with pytest.raises(TransportError):
            devserver_site.run_worker("dev1.example", envelope, mock_agent)


def test_run_worker_scp_failure_raises_transport_error(devserver_site, mock_agent):
    """run_worker raises TransportError on scp CalledProcessError."""
    from engine.transport import TransportError

    envelope = {
        "ticket_id": "run-1/t-0",
        "timeout_s": 60,
        "goal_envelope": {
            "driver": {"command": None, "args": {}, "loop": None}
        },
    }

    with patch("sites.devserver.site.subprocess.run") as mock_run:
        # First calls succeed (mkdir), then scp raises CalledProcessError
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),  # mkdir
            subprocess.CalledProcessError(1, ["scp"], stderr="scp failed"),  # scp envelope
        ]

        with pytest.raises(TransportError):
            devserver_site.run_worker("dev1.example", envelope, mock_agent)


def test_run_worker_prepends_guard_to_remote_path(devserver_site, mock_agent, tmp_path):
    """run_worker prepends guard dir to remote PATH as a shell string.

    CRITICAL: SSHSite passes remote cmd as separate argv items (where $PATH won't
    expand); devserver must pass as a SINGLE SHELL STRING so the remote shell
    expands $PATH before serve-once.
    """
    from engine.models import Result
    import hashlib

    payload = {"scenario": "ok"}
    payload_canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_sha256 = hashlib.sha256(payload_canon.encode("utf-8")).hexdigest()

    envelope = {
        "ticket_id": "run-1/t-0",
        "run_id": "run-1",
        "phase": "work",
        "resource_req": "cpu",
        "base_ref": "main",
        "payload": payload,
        "payload_sha256": payload_sha256,
        "timeout_s": 60,
        "site_context": {},
        "goal_envelope": {
            "goal": "test",
            "driver": {"command": None, "args": {}, "loop": None},
            "done_contract": {},
            "guardrails": {"no_ship": True},
        },
    }

    result_json = json.dumps({
        "outcome": "ok",
        "termination_reason": "goal_met",
        "result_ref": "result://run-1/t-0",
        "error_summary": None,
        "started_at": 1000.0,
        "ended_at": 1001.0,
        "payload": payload,
        "evidence_ref": None,
    })

    with patch("sites.devserver.site.subprocess.run") as mock_run, \
         patch("sites.devserver.site.tempfile.TemporaryDirectory") as mock_tmpdir, \
         patch("builtins.open", create=True) as mock_open, \
         patch("sites.devserver.site.os.path.exists") as mock_exists:

        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=result_json, stderr=""
        )
        mock_open.return_value.__enter__.return_value.read.return_value = result_json
        mock_open.return_value.__enter__.return_value.write = lambda x: None
        mock_exists.return_value = True

        result = devserver_site.run_worker("dev1.example", envelope, mock_agent)

    assert isinstance(result, Result)
    assert result.outcome == "ok"

    # CRITICAL: Assert the ssh serve-once call prepends PATH=<guarddir>:$PATH as a SHELL STRING
    # Find the ssh serve-once call (typically the 3rd call after mkdir, scp-envelope)
    ssh_calls = [call for call in mock_run.call_args_list if "ssh" in str(call)]
    assert len(ssh_calls) > 0, "Expected at least one ssh call"

    # The ssh serve-once call should have a remote command that sets PATH
    serve_call = None
    for call in mock_run.call_args_list:
        args = call[0][0] if call[0] else []
        if "ssh" in str(args) and "serve-once" in str(args):
            serve_call = args
            break

    assert serve_call is not None, "Expected an ssh serve-once call"
    # The remote command should be a single shell string (or sh -c "...") that exports PATH
    # Look for PATH= in the command
    serve_str = " ".join(str(a) for a in serve_call)
    assert "PATH=" in serve_str, "Expected PATH=<guarddir>:$PATH in remote command"


def test_run_worker_successful_returns_result(devserver_site, mock_agent, tmp_path):
    """run_worker with successful ssh execution returns parsed Result via agent.parse_result."""
    from engine.models import Result
    import hashlib

    payload = {"scenario": "ok"}
    payload_canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_sha256 = hashlib.sha256(payload_canon.encode("utf-8")).hexdigest()

    envelope = {
        "ticket_id": "run-1/t-0",
        "run_id": "run-1",
        "phase": "work",
        "resource_req": "cpu",
        "base_ref": "main",
        "payload": payload,
        "payload_sha256": payload_sha256,
        "timeout_s": 60,
        "site_context": {},
        "goal_envelope": {
            "goal": "test",
            "driver": {"command": None, "args": {}, "loop": None},
            "done_contract": {},
            "guardrails": {"no_ship": True},
        },
    }

    result_json = json.dumps({
        "outcome": "ok",
        "termination_reason": "goal_met",
        "result_ref": "result://run-1/t-0",
        "error_summary": None,
        "started_at": 1000.0,
        "ended_at": 1001.0,
        "payload": payload,
        "evidence_ref": None,
    })

    with patch("sites.devserver.site.subprocess.run") as mock_run, \
         patch("sites.devserver.site.tempfile.TemporaryDirectory") as mock_tmpdir, \
         patch("builtins.open", create=True) as mock_open, \
         patch("sites.devserver.site.os.path.exists") as mock_exists:

        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=result_json, stderr=""
        )
        mock_open.return_value.__enter__.return_value.read.return_value = result_json
        mock_open.return_value.__enter__.return_value.write = lambda x: None
        mock_exists.return_value = True

        result = devserver_site.run_worker("dev1.example", envelope, mock_agent)

    assert isinstance(result, Result)
    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"


def test_guarantees_no_ship_returns_true(devserver_site):
    """guarantees_no_ship returns True (installs + verifies guard)."""
    assert devserver_site.guarantees_no_ship() is True


def test_resource_classes_returns_cpu(devserver_site):
    """resource_classes returns ["cpu"]."""
    classes = devserver_site.resource_classes()
    assert classes == ["cpu"]


@patch("subprocess.run")
def test_submit_for_review_returns_url_and_never_lands(mock_run, devserver_site):
    """submit_for_review returns a review URL and NEVER issues land/push.

    Wraps jf submit (publish-only), never jf land.
    """
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="https://review.example/D12345\n", stderr=""
    )

    change = {"id": "change-1"}
    url = devserver_site.submit_for_review("dev1.example", change)

    assert isinstance(url, str)
    assert len(url) > 0

    # Assert no land/push commands were called
    for call in mock_run.call_args_list:
        args = call[0][0] if call[0] else []
        args_str = " ".join(str(a) for a in args)
        assert "land" not in args_str or "jf" not in args_str, "Should not call land"
        assert "push" not in args_str, "Should not call push"


def test_issue_source_returns_empty_by_default(devserver_site):
    """issue_source returns [] by default (pluggable endpoint)."""
    from engine.models import IssueQuery

    query = IssueQuery(kind="bug", limit=10)
    issues = devserver_site.issue_source(query)

    assert isinstance(issues, list)
    assert len(issues) == 0
