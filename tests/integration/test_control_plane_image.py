"""Control plane image integration tests.

STATIC assertions (no Docker needed) verify the Dockerfile/compose contracts:
- Dockerfile pip installs .[server] (resolves FastAPI/uvicorn)
- compose binds 127.0.0.1 by default, sets HERMES_LOG_FORMAT=json, named volume

DOCKER e2e (@pytest.mark.docker, skip cleanly when absent) builds + runs the
image and verifies the API server starts, migrations apply, /api/health returns 200.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

_ENGINE = shutil.which("podman") or shutil.which("docker")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMAGE = "hermes-control-plane:pytest"
_CONTAINER_NAME = "hermes-control-plane-pytest"


# --- STATIC tests (run in normal suite: -m "not docker") -------------------


def test_dockerfile_installs_server_extra():
    """STATIC: Dockerfile installs .[server] extra (grep the build file)."""
    dockerfile = _REPO_ROOT / "fleet" / "Dockerfile.control-plane"
    # At this point the file doesn't exist (RED), so this will fail
    assert dockerfile.exists(), f"Dockerfile not found: {dockerfile}"

    content = dockerfile.read_text()
    # Verify it installs the server extra (either .[server] or similar)
    assert "pip install" in content, "Dockerfile must pip install"
    assert "[server]" in content, "Dockerfile must install .[server] extra"


def test_compose_loopback_bind_default():
    """STATIC: compose file binds 127.0.0.1 by default."""
    compose_file = _REPO_ROOT / "fleet" / "docker-compose.control-plane.yml"
    assert compose_file.exists(), f"Compose file not found: {compose_file}"

    content = compose_file.read_text()
    # The compose should bind 127.0.0.1 (loopback default)
    assert "127.0.0.1" in content, "Compose must bind 127.0.0.1 by default"


def test_compose_sets_json_log_format():
    """STATIC: compose sets HERMES_LOG_FORMAT=json."""
    compose_file = _REPO_ROOT / "fleet" / "docker-compose.control-plane.yml"
    assert compose_file.exists(), f"Compose file not found: {compose_file}"

    content = compose_file.read_text()
    assert "HERMES_LOG_FORMAT" in content, "Compose must set HERMES_LOG_FORMAT"
    assert "json" in content, "HERMES_LOG_FORMAT must be json"


def test_compose_mounts_named_hermes_home_volume():
    """STATIC: compose mounts a named HERMES_HOME volume."""
    compose_file = _REPO_ROOT / "fleet" / "docker-compose.control-plane.yml"
    assert compose_file.exists(), f"Compose file not found: {compose_file}"

    content = compose_file.read_text()
    # Should have a volumes section and mount HERMES_HOME
    assert "volumes:" in content, "Compose must declare volumes"
    assert "HERMES_HOME" in content, "Compose must mount HERMES_HOME"


# --- DOCKER e2e (skip when docker/podman absent) ----------------------------


def _sh(*args, check=True, timeout=300):
    return subprocess.run(
        list(args), capture_output=True, text=True, check=check, timeout=timeout
    )


def _rm_container():
    subprocess.run(
        [_ENGINE, "rm", "-f", _CONTAINER_NAME],
        capture_output=True, text=True,
    )


def _rm_volume():
    subprocess.run(
        [_ENGINE, "volume", "rm", "-f", "hermes-home-pytest"],
        capture_output=True, text=True,
    )


@pytest.mark.docker
@pytest.mark.skipif(_ENGINE is None, reason="podman/docker not available")
def test_control_plane_image_e2e(tmp_path):
    """DOCKER e2e: build, run, GET /api/health returns 200, migrations applied."""
    # Build the control-plane image
    _sh(_ENGINE, "build", "--network=host", "-f",
        str(_REPO_ROOT / "fleet" / "Dockerfile.control-plane"),
        "-t", _IMAGE, str(_REPO_ROOT), timeout=600)

    _rm_container()
    _rm_volume()

    try:
        # Create a named volume for HERMES_HOME
        _sh(_ENGINE, "volume", "create", "hermes-home-pytest")

        # Run the control plane container
        # Bind to loopback on host port 18080 (to avoid conflicts in test environment)
        # Server inside container binds to 0.0.0.0 so it's accessible via port mapping
        _sh(_ENGINE, "run", "-d", "--name", _CONTAINER_NAME,
            "-p", "127.0.0.1:18080:8080",
            "-v", "hermes-home-pytest:/hermes-home",
            "-e", "HERMES_HOME=/hermes-home",
            "-e", "HERMES_BIND=0.0.0.0",
            "-e", "HERMES_LOG_FORMAT=json",
            _IMAGE)

        # Wait for the API server to start and get the token
        # Since the server binds to 0.0.0.0, it requires auth even via loopback host access
        deadline = time.monotonic() + 30
        token = None
        health_ok = False

        while time.monotonic() < deadline:
            try:
                # First, try to read the token from the volume
                if token is None:
                    result = _sh(_ENGINE, "exec", _CONTAINER_NAME,
                                "cat", "/hermes-home/api_token", check=False)
                    if result.returncode == 0:
                        token = result.stdout.strip()

                # If we have a token, check health with auth
                if token:
                    result = subprocess.run(
                        ["curl", "-s", "-f", "-H", f"Authorization: Bearer {token}",
                         "http://127.0.0.1:18080/api/health"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        if data.get("status") == "ok":
                            health_ok = True
                            break
            except Exception:
                pass
            time.sleep(0.5)

        assert health_ok, "API server never became healthy"
        assert token is not None, "Token file never appeared"

        # Verify queue.db exists in the volume and has migrations applied
        # Run a command in the container to check
        result = _sh(_ENGINE, "exec", _CONTAINER_NAME,
                    "sh", "-c", "test -f /hermes-home/queue.db && echo ok")
        assert "ok" in result.stdout, "queue.db not found in HERMES_HOME volume"

        # Check that migrations table exists (proves migrations ran)
        result = _sh(_ENGINE, "exec", _CONTAINER_NAME,
                    "sh", "-c",
                    "sqlite3 /hermes-home/queue.db 'SELECT COUNT(*) FROM schema_migrations'")
        assert result.returncode == 0, "schema_migrations table not found"
        count = int(result.stdout.strip())
        assert count > 0, "No migrations applied"

    finally:
        _rm_container()
        _rm_volume()
