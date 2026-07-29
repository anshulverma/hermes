"""Static assertions on the systemd service-unit example.

Validates the shape of fleet/hermes-control-plane.service without running systemd.
The unit file is a documented artifact; its contract is the set of keys we assert.
"""
import configparser
from pathlib import Path


def test_service_unit_exists():
    """The example systemd unit exists at fleet/hermes-control-plane.service."""
    unit_path = Path(__file__).parent.parent.parent / "fleet" / "hermes-control-plane.service"
    assert unit_path.exists(), "fleet/hermes-control-plane.service must exist"


def test_service_unit_shape():
    """Assert the required systemd unit keys for SIGTERM-graceful and restart policy."""
    unit_path = Path(__file__).parent.parent.parent / "fleet" / "hermes-control-plane.service"

    # Parse as INI-style config (systemd unit format)
    # Allow duplicate keys for systemd's multi-valued Environment= lines
    parser = configparser.ConfigParser(strict=False)
    parser.read(unit_path)

    # Service section must exist
    assert "Service" in parser.sections(), "Unit must have [Service] section"
    service = parser["Service"]

    # SIGTERM signal for graceful shutdown (D5)
    assert service.get("KillSignal") == "SIGTERM", "Must use SIGTERM for graceful shutdown"

    # Restart policy
    assert service.get("Restart") == "on-failure", "Must restart on failure"

    # Stop timeout must exist and be numeric
    timeout_str = service.get("TimeoutStopSec")
    assert timeout_str is not None, "TimeoutStopSec must be set"
    # ConfigParser preserves the raw value; strip any unit suffix (e.g. "90s" → "90")
    timeout_numeric = timeout_str.rstrip("s")
    assert timeout_numeric.isdigit(), f"TimeoutStopSec must be numeric (got {timeout_str})"
    assert int(timeout_numeric) > 0, "TimeoutStopSec must be positive"

    # ExecStart must invoke hermes serve --api
    exec_start = service.get("ExecStart", "")
    assert "hermes serve --api" in exec_start, "ExecStart must invoke 'hermes serve --api'"


def test_service_unit_environment():
    """Assert HERMES_LOG_FORMAT=json is set in the unit environment."""
    unit_path = Path(__file__).parent.parent.parent / "fleet" / "hermes-control-plane.service"

    # Systemd allows multiple Environment= lines; check raw file for required env var
    with open(unit_path) as f:
        unit_text = f.read()

    assert "HERMES_LOG_FORMAT=json" in unit_text, "Unit must set HERMES_LOG_FORMAT=json"
