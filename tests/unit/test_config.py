"""Unit tests for engine/config.py

Tests for HERMES_HOME resolution, env var defaults, and networked-mount guard.
"""
import os
import tempfile
from pathlib import Path
import pytest


def test_resolve_home_default():
    """resolve_home() defaults to ~/.hermes when HERMES_HOME is unset."""
    from engine.config import resolve_home

    # Clear HERMES_HOME if set
    old_val = os.environ.pop('HERMES_HOME', None)
    try:
        home = resolve_home()
        assert home == Path.home() / '.hermes'
    finally:
        if old_val is not None:
            os.environ['HERMES_HOME'] = old_val


def test_resolve_home_from_env():
    """resolve_home() honors HERMES_HOME when set."""
    from engine.config import resolve_home

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        try:
            home = resolve_home()
            assert home == Path(tmpdir)
        finally:
            os.environ.pop('HERMES_HOME', None)


def test_resolve_home_rejects_networked_mount():
    """resolve_home() rejects a path on a networked mount with a clear error."""
    from engine.config import resolve_home, ConfigError

    with tempfile.TemporaryDirectory() as tmpdir:
        # Use an injectable networked-filesystem probe for testing
        def fake_networked_probe(path):
            # Our fake says this tmpdir is networked
            return str(path).startswith(tmpdir)

        os.environ['HERMES_HOME'] = tmpdir
        try:
            with pytest.raises(ConfigError) as exc_info:
                resolve_home(is_networked=fake_networked_probe)

            # Should have a clear error message naming the path
            assert tmpdir in str(exc_info.value)
            assert 'network' in str(exc_info.value).lower()
        finally:
            os.environ.pop('HERMES_HOME', None)


def test_default_networked_check_no_personal_paths():
    """Default networked check has no hardcoded personal paths."""
    from engine.config import _default_networked_check
    import inspect

    # Read the source code
    source = inspect.getsource(_default_networked_check)

    # Should NOT contain personal paths
    assert '/home/anshulverma/' not in source, \
        "Default networked check should not hardcode personal paths"


def test_env_defaults():
    """Config provides correct defaults for all env vars."""
    from engine.config import heartbeat_s, site, agent

    # Clear all HERMES_* env vars
    old_vals = {}
    for key in list(os.environ.keys()):
        if key.startswith('HERMES_'):
            old_vals[key] = os.environ.pop(key)

    try:
        assert heartbeat_s() == 30
        assert site() == 'local'
        assert agent() == 'claude'
    finally:
        # Restore
        for key, val in old_vals.items():
            os.environ[key] = val


def test_env_overrides():
    """Config honors environment variable overrides."""
    from engine.config import heartbeat_s, site, agent

    os.environ['HERMES_HEARTBEAT_S'] = '60'
    os.environ['HERMES_SITE'] = 'test-site'
    os.environ['HERMES_AGENT'] = 'test-agent'

    try:
        # Functions read fresh env at call time (no reload needed)
        assert heartbeat_s() == 60
        assert site() == 'test-site'
        assert agent() == 'test-agent'
    finally:
        os.environ.pop('HERMES_HEARTBEAT_S', None)
        os.environ.pop('HERMES_SITE', None)
        os.environ.pop('HERMES_AGENT', None)
