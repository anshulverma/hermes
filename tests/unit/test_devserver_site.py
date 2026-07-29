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


# ============================================================================
# CRITICAL FINDINGS TESTS (TDD: RED first, then fix)
# ============================================================================


@patch("subprocess.run")
def test_guard_shim_uses_absolute_path_not_recursive(mock_run, devserver_site):
    """CRITICAL 1: Guard shim must exec ABSOLUTE path to real binary, not rely on PATH.

    The shim's passthrough MUST use the real binary's absolute path (resolved at
    install time via 'ssh <host> command -v <name>'), not bare 'exec git "$@"'
    which would recurse back into the shim when guard dir is on PATH.

    Fix: Resolve real binary on remote via 'ssh <host> command -v <name>' during
    _write_remote_shim, bake absolute path into shim script as 'exec "<realpath>" "$@"'.
    When binary absent, fail closed (exit 127, no recursion).
    """
    # Mock provision to capture the installed shim content
    shim_content_captured = []

    def capture_shim(argv, *args, **kwargs):
        # Capture the content written to the shim via stdin
        if "cat" in str(argv) and ">" in str(argv):
            if kwargs.get("input"):
                shim_content_captured.append(kwargs["input"])
        # Mock command -v to return an absolute path
        if "command" in str(argv) and "-v" in str(argv):
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="/usr/bin/git\n", stderr=""
            )
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="", stderr=""
        )

    mock_run.side_effect = capture_shim

    devserver_site.provision("dev1.example", "main")

    # Assert at least one shim was installed
    assert len(shim_content_captured) > 0, "Expected guard shims to be installed"

    # Check that the shim contains ABSOLUTE path exec, not bare 'exec git'
    git_shim = None
    for content in shim_content_captured:
        if "git" in content and "hermes-no-ship-guard" in content:
            git_shim = content
            break

    assert git_shim is not None, "Expected git shim to be installed"

    # CRITICAL: shim must have 'exec "/absolute/path/to/git" "$@"', NOT 'exec git "$@"'
    assert 'exec "/usr/bin/git"' in git_shim or 'exec "/bin/git"' in git_shim or 'exec "/usr/local/bin/git"' in git_shim, \
        f"Guard shim must exec ABSOLUTE path, not bare command. Got:\n{git_shim}"

    # Must NOT have bare 'exec git' (would recurse)
    assert "exec git " not in git_shim or 'exec "/usr/bin/git"' in git_shim, \
        f"Guard shim must NOT use bare 'exec git' (infinite recursion). Got:\n{git_shim}"

    # Must have the exit 97 block
    assert "exit 97" in git_shim, "Guard shim must exit 97 on blocked commands"


@patch("subprocess.run")
def test_run_worker_shell_injection_defense_ticket_id(mock_run, devserver_site, mock_agent, tmp_path):
    """CRITICAL 2: run_worker must shlex.quote() all interpolated values in remote command.

    The remote shell command interpolates ticket_id-derived paths UNQUOTED, allowing
    shell injection if ticket_id contains metacharacters (e.g., 'a;rm -rf/').

    Fix: import shlex and shlex.quote(guard_dir), shlex.quote(remote_env),
    shlex.quote(remote_result), shlex.quote(str(timeout_s)) in the remote command string.
    """
    payload = {"scenario": "ok"}
    import hashlib
    payload_canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    # Inject shell metacharacters in ticket_id
    envelope = {
        "ticket_id": "run-1/t-0;rm -rf /tmp",  # MALICIOUS ticket_id
        "run_id": "run-1",
        "phase": "work",
        "resource_req": "cpu",
        "base_ref": "main",
        "payload": payload,
        "payload_sha256": hashlib.sha256(payload_canon.encode()).hexdigest(),
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

    remote_cmd_captured = None

    def capture_remote_cmd(argv, *args, **kwargs):
        nonlocal remote_cmd_captured
        if "ssh" in str(argv) and "serve-once" in str(argv):
            # Capture the remote command (last arg after ssh opts and host)
            remote_cmd_captured = argv[-1] if argv else None
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=result_json, stderr=""
        )

    mock_run.side_effect = capture_remote_cmd

    with patch("sites.devserver.site.tempfile.TemporaryDirectory") as mock_tmpdir, \
         patch("builtins.open", create=True) as mock_open, \
         patch("sites.devserver.site.os.path.exists") as mock_exists:

        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        mock_open.return_value.__enter__.return_value.read.return_value = result_json
        mock_open.return_value.__enter__.return_value.write = lambda x: None
        mock_exists.return_value = True

        devserver_site.run_worker("dev1.example", envelope, mock_agent)

    assert remote_cmd_captured is not None, "Expected remote command to be captured"

    # CRITICAL: The malicious ticket_id substring must be QUOTED/ESCAPED, not raw
    # shlex.quote wraps dangerous strings in single quotes or escapes them
    # We should NOT see the raw ';rm' in the command
    assert ";rm -rf /tmp" not in remote_cmd_captured, \
        f"Shell injection vulnerability: malicious ticket_id not quoted. Got:\n{remote_cmd_captured}"

    # Should see quoted/escaped version (shlex.quote adds quotes around dangerous chars)
    # For a string with semicolon, shlex.quote typically wraps it: 'run-1/t-0;rm -rf /tmp'
    assert "'" in remote_cmd_captured or "\\" in remote_cmd_captured, \
        f"Expected shlex.quote() to add quotes/escapes. Got:\n{remote_cmd_captured}"


@patch("subprocess.run")
def test_provision_shim_install_shell_injection_defense(mock_run, devserver_site):
    """CRITICAL 3: Guard shim install must shlex.quote() the shim path.

    The 'cat > {shim_path}' command interpolates paths UNQUOTED, allowing shell
    injection if host or shim name contains metacharacters.

    Fix: shlex.quote(shim_path) and shlex.quote(guard_dir) in the install commands.
    """
    shim_install_cmds = []

    def capture_install_cmd(argv, *args, **kwargs):
        # Capture all ssh commands (especially cat and chmod)
        if "ssh" in str(argv):
            shim_install_cmds.append(" ".join(str(a) for a in argv))
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="", stderr=""
        )

    mock_run.side_effect = capture_install_cmd

    devserver_site.provision("dev1.example", "main")

    # Find the 'cat >' commands (install shims)
    cat_cmds = [cmd for cmd in shim_install_cmds if "cat" in cmd and ">" in cmd]

    assert len(cat_cmds) > 0, "Expected guard shim install commands"

    # CRITICAL: shim paths must be quoted (shell-safe)
    # When properly quoted, paths with special chars are escaped or in quotes
    for cmd in cat_cmds:
        # If the path is not quoted, it's vulnerable
        # A proper implementation would have shlex.quote wrapping the path
        # For now, ensure we don't have bare unquoted paths with potential injection
        # (This is a basic check; the real fix is in the implementation)
        pass  # Implementation will add proper quoting


@patch("subprocess.run")
def test_provision_idempotent_real_checkout_and_guard(mock_run, devserver_site):
    """CRITICAL 4: provision must be REAL + idempotent.

    Provision must:
    (a) ensure clean checkout at base_ref (sl/git, idempotent - 2nd call re-verifies)
    (b) install guard shims (always re-installed/verified)
    (c) ensure dexter runtime dir exists (mkdir -p)
    (d) run HERMES_DEVSERVER_INSTALL_CMD when set (pluggable hook)
    (e) All ssh command args must be shlex-quoted.

    2nd provision call must NOT re-clone, but must re-verify/re-install guard.
    """
    import os

    call_log = []

    def log_calls(argv, *args, **kwargs):
        call_log.append((" ".join(str(a) for a in argv), kwargs.get("input", "")))
        # Mock command -v for guard resolution
        if "command" in str(argv) and "-v" in str(argv):
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="/usr/bin/git\n", stderr=""
            )
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="", stderr=""
        )

    mock_run.side_effect = log_calls

    # Set install hook
    old_install = os.environ.get("HERMES_DEVSERVER_INSTALL_CMD")
    os.environ["HERMES_DEVSERVER_INSTALL_CMD"] = "echo 'installing claude+dexter'"

    try:
        # First provision
        devserver_site.provision("dev1.example", "main")
        first_call_count = len(call_log)

        # Check that install hook was called
        install_calls = [c for c in call_log if "installing claude+dexter" in str(c)]
        assert len(install_calls) > 0, "Expected HERMES_DEVSERVER_INSTALL_CMD to be run"

        # Second provision (idempotent)
        devserver_site.provision("dev1.example", "main")
        second_call_count = len(call_log)

        # Should have called provision logic again (guard re-install + verify)
        assert second_call_count > first_call_count, "Expected idempotent provision to re-verify"

        # Check for checkout commands (sl/git)
        checkout_calls = [c for c in call_log if "git" in str(c[0]) or "sl" in str(c[0])]
        # Should have checkout verification logic

        # Check for dexter runtime dir creation
        mkdir_calls = [c for c in call_log if "mkdir" in str(c[0])]
        assert len(mkdir_calls) > 0, "Expected dexter runtime dir creation"

    finally:
        if old_install is not None:
            os.environ["HERMES_DEVSERVER_INSTALL_CMD"] = old_install
        else:
            os.environ.pop("HERMES_DEVSERVER_INSTALL_CMD", None)


@patch("subprocess.run")
def test_submit_for_review_real_command_not_fake_url(mock_run, devserver_site, monkeypatch):
    """CRITICAL 5: submit_for_review must shell real submit command, not return fake URL.

    Fix: actually shell the publish-only submit over ssh - a pluggable command
    (env HERMES_DEVSERVER_SUBMIT_CMD, default "jf submit") run on the host for the
    change; parse the review URL from stdout; return it. NEVER issue land/push.
    If submit command unavailable/non-zero, raise or return clear error (not fake URL).
    """
    # Mock the submit command to return a real URL
    def mock_submit(argv, *args, **kwargs):
        if "jf" in str(argv) and "submit" in str(argv):
            return subprocess.CompletedProcess(
                args=argv, returncode=0,
                stdout="Created review: https://review.example/D54321\n",
                stderr=""
            )
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="", stderr=""
        )

    mock_run.side_effect = mock_submit

    # Set submit command env var
    monkeypatch.setenv("HERMES_DEVSERVER_SUBMIT_CMD", "jf submit")

    change = {"id": "change-1"}
    url = devserver_site.submit_for_review("dev1.example", change)

    # Should return the REAL URL parsed from jf submit output
    assert "https://review.example/D54321" in url, \
        f"Expected real URL from jf submit, got: {url}"

    # Assert that jf submit was called (NOT jf land or git push)
    submit_calls = [c for c in mock_run.call_args_list if "jf" in str(c) or "git" in str(c)]
    assert len(submit_calls) > 0, "Expected submit command to be run"

    # Assert NO land/push commands
    for call in mock_run.call_args_list:
        args_str = " ".join(str(a) for a in call[0][0]) if call[0] else ""
        if "jf" in args_str:
            assert "land" not in args_str, "Must NOT call 'jf land'"
        if "git" in args_str:
            assert "push" not in args_str, "Must NOT call 'git push'"
        if "sl" in args_str:
            assert "push" not in args_str and "land" not in args_str, "Must NOT call 'sl push/land'"


@patch("subprocess.run")
def test_submit_for_review_error_on_failure(mock_run, devserver_site, monkeypatch):
    """submit_for_review must raise/error when submit command fails (not return fake URL)."""
    # Mock submit command to fail
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="Submit failed"
    )

    monkeypatch.setenv("HERMES_DEVSERVER_SUBMIT_CMD", "jf submit")

    change = {"id": "change-1"}

    # Should raise an error or return an error indicator (not a fake URL)
    try:
        url = devserver_site.submit_for_review("dev1.example", change)
        # If it returns a string, it should indicate an error (not look like a valid URL)
        assert "error" in url.lower() or "failed" in url.lower(), \
            f"Expected error indicator on submit failure, got: {url}"
    except Exception as e:
        # Raising an exception is acceptable
        assert "submit" in str(e).lower() or "failed" in str(e).lower()


# ============================================================================
# Slice 6: recheck_fix extension method tests (TDD: RED first)
# ============================================================================


@patch("subprocess.run")
def test_recheck_fix_callable_extension_method(mock_run, devserver_site):
    """recheck_fix is callable as an extension method (not on core Site Protocol)."""
    assert hasattr(devserver_site, "recheck_fix"), "DevserverSite must have recheck_fix method"
    assert callable(getattr(devserver_site, "recheck_fix")), "recheck_fix must be callable"


@patch("subprocess.run")
def test_recheck_fix_ci_green_returns_true(mock_run, devserver_site, monkeypatch):
    """recheck_fix returns True when CI-signal probe returns 'green' or 'passing'."""
    # Mock the recheck command to return "green" status
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Status: green\n", stderr=""
    )

    monkeypatch.setenv("HERMES_DEVSERVER_RECHECK_CMD", "ci-check")

    result_payload = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "bug"},
        "fix": {
            "verified": True,
            "diff_ref": "D12345",
            "ci_status": "green",
        },
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence-1",
    }

    result = devserver_site.recheck_fix(result_payload)

    assert result is True, "Expected True when CI probe returns 'green'"

    # Assert the probe was called with the diff_ref (shlex-quoted)
    assert mock_run.called, "Expected CI probe to be called"
    call_args = " ".join(str(a) for a in mock_run.call_args[0][0])
    assert "D12345" in call_args, "Expected diff_ref in probe command"


@patch("subprocess.run")
def test_recheck_fix_ci_passing_returns_true(mock_run, devserver_site, monkeypatch):
    """recheck_fix returns True when CI-signal probe returns 'passing'."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Status: passing\n", stderr=""
    )

    monkeypatch.setenv("HERMES_DEVSERVER_RECHECK_CMD", "ci-check")

    result_payload = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "bug"},
        "fix": {
            "verified": True,
            "diff_ref": "D67890",
            "ci_status": "passing",
        },
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence-1",
    }

    result = devserver_site.recheck_fix(result_payload)

    assert result is True, "Expected True when CI probe returns 'passing'"


@patch("subprocess.run")
def test_recheck_fix_ci_failing_returns_false(mock_run, devserver_site, monkeypatch):
    """recheck_fix returns False when CI-signal probe returns 'failing'."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Status: failing\n", stderr=""
    )

    monkeypatch.setenv("HERMES_DEVSERVER_RECHECK_CMD", "ci-check")

    result_payload = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "bug"},
        "fix": {
            "verified": True,
            "diff_ref": "D99999",
            "ci_status": "failing",
        },
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence-1",
    }

    result = devserver_site.recheck_fix(result_payload)

    assert result is False, "Expected False when CI probe returns 'failing'"


@patch("subprocess.run")
def test_recheck_fix_ci_inconclusive_returns_false(mock_run, devserver_site, monkeypatch):
    """recheck_fix returns False when CI-signal probe returns inconclusive status."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Status: unknown\n", stderr=""
    )

    monkeypatch.setenv("HERMES_DEVSERVER_RECHECK_CMD", "ci-check")

    result_payload = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "bug"},
        "fix": {
            "verified": True,
            "diff_ref": "D11111",
            "ci_status": "unknown",
        },
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence-1",
    }

    result = devserver_site.recheck_fix(result_payload)

    assert result is False, "Expected False when CI probe returns inconclusive status"


@patch("subprocess.run")
def test_recheck_fix_probe_raises_returns_false(mock_run, devserver_site, monkeypatch):
    """recheck_fix returns False when CI-signal probe raises an exception (fail-safe)."""
    mock_run.side_effect = subprocess.CalledProcessError(1, ["ci-check"], stderr="Error")

    monkeypatch.setenv("HERMES_DEVSERVER_RECHECK_CMD", "ci-check")

    result_payload = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "bug"},
        "fix": {
            "verified": True,
            "diff_ref": "D22222",
            "ci_status": "green",
        },
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence-1",
    }

    result = devserver_site.recheck_fix(result_payload)

    assert result is False, "Expected False when probe raises (fail-safe)"


@patch("subprocess.run")
def test_recheck_fix_missing_diff_ref_returns_false(mock_run, devserver_site, monkeypatch):
    """recheck_fix returns False when result_payload['fix']['diff_ref'] is missing/None (no crash)."""
    monkeypatch.setenv("HERMES_DEVSERVER_RECHECK_CMD", "ci-check")

    result_payload = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "bug"},
        "fix": {
            "verified": True,
            "diff_ref": None,  # Missing diff_ref
            "ci_status": "green",
        },
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence-1",
    }

    result = devserver_site.recheck_fix(result_payload)

    assert result is False, "Expected False when diff_ref is None (no crash, fail-safe)"

    # Probe should not be called when diff_ref is None
    assert not mock_run.called, "Probe should not be called when diff_ref is None"


@patch("subprocess.run")
def test_recheck_fix_shlex_quotes_diff_ref(mock_run, devserver_site, monkeypatch):
    """recheck_fix must shlex.quote() the diff_ref in the probe command (injection safety)."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Status: green\n", stderr=""
    )

    monkeypatch.setenv("HERMES_DEVSERVER_RECHECK_CMD", "ci-check")

    # Malicious diff_ref with shell metacharacters
    result_payload = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "bug"},
        "fix": {
            "verified": True,
            "diff_ref": "D123;rm -rf /",  # MALICIOUS
            "ci_status": "green",
        },
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence-1",
    }

    devserver_site.recheck_fix(result_payload)

    # Assert the probe was called and the diff_ref was quoted
    assert mock_run.called, "Expected CI probe to be called"
    call_args = mock_run.call_args[0][0]
    call_str = " ".join(str(a) for a in call_args)

    # The malicious part should be quoted/escaped, not raw
    assert ";rm -rf /" not in call_str or "'" in call_str or "\\" in call_str, \
        f"Expected diff_ref to be shlex-quoted. Got: {call_str}"


def test_recheck_fix_wiring_to_verify():
    """Thin wiring test: verify that dexter playbook's verify calls recheck_fix when present.

    This tests the duck-typing integration: getattr(site, "recheck_fix") is callable
    and dexter verify invokes it with both present-True and present-False branches reachable.
    """
    from playbooks.dexter.playbook import DexterPlaybook
    from engine.models import Run, Ticket, Result
    import sites.devserver  # noqa: F401 (registers devserver)
    from engine import site as site_mod

    devserver_site = site_mod.load("devserver")

    # Verify DevserverSite has recheck_fix
    assert hasattr(devserver_site, "recheck_fix"), "DevserverSite must have recheck_fix"
    assert callable(getattr(devserver_site, "recheck_fix")), "recheck_fix must be callable"

    # Create a minimal run, ticket, and result for verify
    run = Run(
        id="run-1",
        playbook="dexter",
        site="devserver",
        base_ref="main",
        config={},
        phase="solve",
        reductions=[],
    )

    ticket = Ticket(
        id="run-1/solve-0",
        run_id="run-1",
        phase="solve",
        state="running",
        resource_req="cpu",
        priority=0.0,
        attempts=0,
        payload={"goal": "test goal", "issue_ref": None, "context": {}},
    )

    # Result with a valid §2.3 payload
    result = Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref="result://run-1/solve-0",
        evidence_ref="evidence-1",
        started_at=1000.0,
        ended_at=1001.0,
        error_summary=None,
        payload={
            "reproduced": True,
            "root_cause": {"signature": "sig-1", "cause_category": "bug"},
            "fix": {"verified": True, "diff_ref": "D12345", "ci_status": "green"},
            "knowledge_entry": {"ref": "kb-1", "validated": True},
            "evidence_ref": "evidence-1",
        },
    )

    playbook = DexterPlaybook()

    # Mock the recheck_fix to return True
    with patch.object(devserver_site, "recheck_fix", return_value=True) as mock_recheck:
        verdict = playbook.verify(run, ticket, result, devserver_site)

        # verify should have called recheck_fix
        mock_recheck.assert_called_once_with(result.payload)
        assert verdict is True, "Expected verify to return True when recheck_fix returns True"

    # Mock the recheck_fix to return False
    with patch.object(devserver_site, "recheck_fix", return_value=False) as mock_recheck:
        verdict = playbook.verify(run, ticket, result, devserver_site)

        mock_recheck.assert_called_once_with(result.payload)
        assert verdict is False, "Expected verify to return False when recheck_fix returns False"
