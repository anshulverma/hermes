"""Tests for sites.ssh.SSHSite (spec §4, §8).

TDD: written FIRST. Commands are constructed correctly for provision/health/
run_worker; subprocess is MOCKED (no real SSH). Connection failure (ssh exit
255) -> run_worker raises TransportError; successful worker run -> returns
parsed Result; health parses reachability/latency/guard/resources + merges
agent checks.
"""
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def ssh_site():
    import sites.ssh  # noqa: F401 (registers "ssh")
    from engine import site

    return site.load("ssh")


@pytest.fixture
def mock_agent():
    import testkit  # noqa: F401 (registers "mock")
    from engine import agent

    return agent.load("mock")


def test_ssh_site_registration():
    """SSHSite registers as 'ssh'."""
    import sites.ssh  # noqa: F401
    from engine import site

    s = site.load("ssh")
    assert s.name == "ssh"


def test_discover_hosts_from_env(monkeypatch, ssh_site):
    """discover_hosts reads from HERMES_SSH_HOSTS env var (comma-separated)."""
    monkeypatch.setenv("HERMES_SSH_HOSTS", "host1,host2,host3")
    hosts = ssh_site.discover_hosts()
    assert hosts == ["host1", "host2", "host3"]


def test_discover_hosts_empty_when_no_env(monkeypatch, ssh_site):
    """discover_hosts returns [] when HERMES_SSH_HOSTS is absent."""
    monkeypatch.delenv("HERMES_SSH_HOSTS", raising=False)
    hosts = ssh_site.discover_hosts()
    assert hosts == []


@patch("subprocess.run")
def test_provision_builds_ssh_command(mock_run, ssh_site):
    """provision calls ssh to verify the remote host (checkout, guard, runner)."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="OK\nOK\nOK\n", stderr=""
    )

    ssh_site.provision("worker-1", "main")

    # Should have called ssh to check remote state
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert "ssh" in call_args
    assert "worker-1" in call_args


@patch("subprocess.run")
def test_health_reachability_check(mock_run, ssh_site, mock_agent):
    """health runs 'ssh <host> true' and measures latency."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    report = ssh_site.health("worker-1", mock_agent)

    assert report.reachable is True
    assert report.latency_ms >= 0
    assert any(c.name == "transport" for c in report.checks)


@patch("subprocess.run")
def test_health_unreachable_when_ssh_fails(mock_run, ssh_site, mock_agent):
    """health sets reachable=False when ssh command fails."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=255, stdout="", stderr="Connection refused"
    )

    report = ssh_site.health("worker-1", mock_agent)

    assert report.reachable is False


@patch("subprocess.run")
def test_health_parses_resources_from_config(mock_run, ssh_site, mock_agent, monkeypatch):
    """health reads resources from HERMES_SSH_RESOURCES_<host> env var."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )
    monkeypatch.setenv("HERMES_SSH_RESOURCES_worker-1", '{"cpu":8,"gpu":2}')

    report = ssh_site.health("worker-1", mock_agent)

    assert report.resources == {"cpu": 8, "gpu": 2}


@patch("subprocess.run")
def test_health_merges_agent_checks(mock_run, ssh_site, mock_agent):
    """health includes both site checks and agent checks."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    report = ssh_site.health("worker-1", mock_agent)

    # Should have both site checks (transport, guard, resources) and agent checks
    check_names = {c.name for c in report.checks}
    assert "transport" in check_names
    # Agent checks (from MockAgent)
    assert "agent" in check_names or "auth" in check_names


def test_run_worker_connection_failure_raises_transport_error(ssh_site, mock_agent):
    """run_worker raises TransportError on ssh connection failure (exit 255).

    Exit 255 is ssh's own connection-error code (pre-run failure, host unreachable).
    """
    from engine.transport import TransportError

    envelope = {
        "ticket_id": "run-1/t-0",
        "timeout_s": 60,
        "goal_envelope": {
            "driver": {"command": None, "args": {}, "loop": None}
        },
    }

    # Mock subprocess.run at the sites.ssh.site module level to return ssh connection failure (exit 255)
    with patch("sites.ssh.site.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=255, stdout="", stderr="Connection refused"
        )

        with pytest.raises(TransportError):
            ssh_site.run_worker("worker-1", envelope, mock_agent)


def test_run_worker_timeout_raises_transport_error(ssh_site, mock_agent):
    """run_worker raises TransportError on ssh timeout (host-lost / connection timeout)."""
    from engine.transport import TransportError

    envelope = {
        "ticket_id": "run-1/t-0",
        "timeout_s": 60,
        "goal_envelope": {
            "driver": {"command": None, "args": {}, "loop": None}
        },
    }

    # Mock subprocess.run to raise TimeoutExpired on the ssh call
    with patch("sites.ssh.site.subprocess.run") as mock_run:
        # First two calls (mkdir, scp) succeed, third call (ssh serve-once) times out
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),  # mkdir
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),  # scp envelope
            subprocess.TimeoutExpired(cmd=["ssh"], timeout=120),  # ssh serve-once timeout
        ]

        with pytest.raises(TransportError, match="timed out"):
            ssh_site.run_worker("worker-1", envelope, mock_agent)


def test_run_worker_successful_returns_result(ssh_site, mock_agent, tmp_path):
    """run_worker with successful ssh execution returns parsed Result.

    Also asserts the ssh command construction: mkdir/scp-envelope/ssh-serve/scp-result.
    """
    from engine.models import Result
    import hashlib

    # Compute correct payload_sha256
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

    # Mock successful ssh execution
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

    # Create a fake result file for the test
    result_file = tmp_path / "result.json"
    result_file.write_text(result_json)

    # Mock all subprocess calls and file operations
    with patch("sites.ssh.site.subprocess.run") as mock_run, \
         patch("sites.ssh.site.tempfile.TemporaryDirectory") as mock_tmpdir, \
         patch("builtins.open", create=True) as mock_open:

        # Setup temp directory
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)

        # Mock subprocess.run to succeed (4 calls: mkdir, scp-envelope, ssh-serve, scp-result)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=result_json, stderr=""
        )

        # Mock open to write envelope and read result
        mock_open.return_value.__enter__.return_value.read.return_value = result_json
        mock_open.return_value.__enter__.return_value.write = lambda x: None

        # Mock os.path.exists to return True for result file
        with patch("sites.ssh.site.os.path.exists") as mock_exists:
            mock_exists.return_value = True

            result = ssh_site.run_worker("worker-1", envelope, mock_agent)

    assert isinstance(result, Result)
    assert result.outcome == "ok"

    # Assert the expected ssh command sequence was called
    assert mock_run.call_count == 4, f"Expected 4 subprocess calls, got {mock_run.call_count}"

    # Call 1: mkdir
    mkdir_call = mock_run.call_args_list[0][0][0]
    assert "ssh" in mkdir_call
    assert "worker-1" in mkdir_call
    assert "mkdir" in mkdir_call

    # Call 2: scp envelope
    scp_env_call = mock_run.call_args_list[1][0][0]
    assert "scp" in scp_env_call
    assert any("worker-1:" in arg for arg in scp_env_call), "Expected scp to worker-1"

    # Call 3: ssh serve-once
    ssh_serve_call = mock_run.call_args_list[2][0][0]
    assert "ssh" in ssh_serve_call
    assert "worker-1" in ssh_serve_call
    assert "hermes" in ssh_serve_call
    assert "serve-once" in ssh_serve_call

    # Call 4: scp result back
    scp_result_call = mock_run.call_args_list[3][0][0]
    assert "scp" in scp_result_call
    assert any("worker-1:" in arg for arg in scp_result_call), "Expected scp from worker-1"


def test_resource_classes_returns_classes(ssh_site, monkeypatch):
    """resource_classes returns union of classes from all configured hosts."""
    monkeypatch.setenv("HERMES_SSH_HOSTS", "host1,host2")
    monkeypatch.setenv("HERMES_SSH_RESOURCES_host1", '{"cpu":4}')
    monkeypatch.setenv("HERMES_SSH_RESOURCES_host2", '{"cpu":8,"gpu":2}')

    classes = ssh_site.resource_classes()

    assert set(classes) == {"cpu", "gpu"}


def test_guarantees_no_ship_returns_true(ssh_site):
    """guarantees_no_ship returns True (guard baked into worker image)."""
    assert ssh_site.guarantees_no_ship() is True


def test_submit_for_review_returns_placeholder(ssh_site):
    """submit_for_review returns a placeholder URL (no-op for ssh site)."""
    url = ssh_site.submit_for_review("worker-1", {"id": "change-1"})
    assert isinstance(url, str)
    assert len(url) > 0


def test_issue_source_returns_empty_list(ssh_site):
    """issue_source returns empty list (file-based, no remote issues)."""
    from engine.models import IssueQuery

    query = IssueQuery(kind="test", filters={}, limit=100)
    issues = ssh_site.issue_source(query)
    assert issues == []
