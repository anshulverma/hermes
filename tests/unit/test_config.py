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


def test_bind_defaults():
    """bind() defaults to 127.0.0.1 when HERMES_BIND is unset."""
    from engine.config import bind

    old_val = os.environ.pop('HERMES_BIND', None)
    try:
        assert bind() == '127.0.0.1'
    finally:
        if old_val is not None:
            os.environ['HERMES_BIND'] = old_val


def test_bind_from_env(monkeypatch):
    """bind() honors HERMES_BIND when set."""
    from engine.config import bind

    monkeypatch.setenv('HERMES_BIND', '0.0.0.0')
    assert bind() == '0.0.0.0'


def test_ws_poll_s_defaults():
    """ws_poll_s() defaults to 1.0 when HERMES_WS_POLL_S is unset."""
    from engine.config import ws_poll_s

    old_val = os.environ.pop('HERMES_WS_POLL_S', None)
    try:
        assert ws_poll_s() == 1.0
    finally:
        if old_val is not None:
            os.environ['HERMES_WS_POLL_S'] = old_val


def test_ws_poll_s_from_env(monkeypatch):
    """ws_poll_s() honors HERMES_WS_POLL_S and coerces to float."""
    from engine.config import ws_poll_s

    monkeypatch.setenv('HERMES_WS_POLL_S', '2.5')
    assert ws_poll_s() == 2.5


def test_web_dist_defaults():
    """web_dist() defaults to web/dist when HERMES_WEB_DIST is unset."""
    from engine.config import web_dist

    old_val = os.environ.pop('HERMES_WEB_DIST', None)
    try:
        assert web_dist() == 'web/dist'
    finally:
        if old_val is not None:
            os.environ['HERMES_WEB_DIST'] = old_val


def test_web_dist_from_env(monkeypatch):
    """web_dist() honors HERMES_WEB_DIST when set."""
    from engine.config import web_dist

    monkeypatch.setenv('HERMES_WEB_DIST', 'custom/dist')
    assert web_dist() == 'custom/dist'


def test_log_level_defaults():
    """log_level() defaults to INFO when HERMES_LOG_LEVEL is unset."""
    from engine.config import log_level

    old_level = os.environ.pop('HERMES_LOG_LEVEL', None)
    old_debug = os.environ.pop('HERMES_DEBUG', None)
    try:
        assert log_level() == 'INFO'
    finally:
        if old_level is not None:
            os.environ['HERMES_LOG_LEVEL'] = old_level
        if old_debug is not None:
            os.environ['HERMES_DEBUG'] = old_debug


def test_log_level_from_env(monkeypatch):
    """log_level() honors HERMES_LOG_LEVEL when set."""
    from engine.config import log_level

    monkeypatch.setenv('HERMES_LOG_LEVEL', 'DEBUG')
    assert log_level() == 'DEBUG'


def test_log_level_debug_fallback(monkeypatch):
    """log_level() returns DEBUG when HERMES_DEBUG is truthy and HERMES_LOG_LEVEL is unset."""
    from engine.config import log_level

    monkeypatch.delenv('HERMES_LOG_LEVEL', raising=False)
    monkeypatch.setenv('HERMES_DEBUG', '1')
    assert log_level() == 'DEBUG'


def test_log_level_explicit_wins_over_debug(monkeypatch):
    """log_level() respects HERMES_LOG_LEVEL even when HERMES_DEBUG is set."""
    from engine.config import log_level

    monkeypatch.setenv('HERMES_LOG_LEVEL', 'WARNING')
    monkeypatch.setenv('HERMES_DEBUG', '1')
    assert log_level() == 'WARNING'


def test_log_format_defaults():
    """log_format() defaults to text when HERMES_LOG_FORMAT is unset."""
    from engine.config import log_format

    old_val = os.environ.pop('HERMES_LOG_FORMAT', None)
    try:
        assert log_format() == 'text'
    finally:
        if old_val is not None:
            os.environ['HERMES_LOG_FORMAT'] = old_val


def test_log_format_from_env(monkeypatch):
    """log_format() honors HERMES_LOG_FORMAT when set."""
    from engine.config import log_format

    monkeypatch.setenv('HERMES_LOG_FORMAT', 'json')
    assert log_format() == 'json'


def test_log_file_defaults_to_none():
    """log_file() defaults to None when HERMES_LOG_FILE is unset."""
    from engine.config import log_file

    old_val = os.environ.pop('HERMES_LOG_FILE', None)
    try:
        assert log_file() is None
    finally:
        if old_val is not None:
            os.environ['HERMES_LOG_FILE'] = old_val


def test_log_file_from_env(monkeypatch):
    """log_file() honors HERMES_LOG_FILE when set."""
    from engine.config import log_file

    monkeypatch.setenv('HERMES_LOG_FILE', '/tmp/hermes.log')
    assert log_file() == '/tmp/hermes.log'


def test_debug_defaults_to_false():
    """debug() defaults to False when HERMES_DEBUG is unset."""
    from engine.config import debug

    old_val = os.environ.pop('HERMES_DEBUG', None)
    try:
        assert debug() is False
    finally:
        if old_val is not None:
            os.environ['HERMES_DEBUG'] = old_val


def test_debug_truthy_values(monkeypatch):
    """debug() returns True for truthy HERMES_DEBUG values."""
    from engine.config import debug

    for val in ['1', 'true', 'True', 'TRUE', 'yes']:
        monkeypatch.setenv('HERMES_DEBUG', val)
        assert debug() is True


def test_debug_falsy_values(monkeypatch):
    """debug() returns False for falsy HERMES_DEBUG values."""
    from engine.config import debug

    for val in ['0', 'false', 'False', 'FALSE', '', 'no']:
        monkeypatch.setenv('HERMES_DEBUG', val)
        assert debug() is False


def test_known_vars_contains_all_non_dynamic_vars():
    """KNOWN_VARS contains all non-dynamic HERMES_*/DEXTER_*/INVESTIGATIONS_DIR vars."""
    from engine.config import KNOWN_VARS

    # All non-dynamic vars from operability.md section 3.1
    required_vars = {
        'HERMES_HOME',
        'HERMES_NETWORKED_PREFIXES',
        'HERMES_SITE',
        'HERMES_AGENT',
        'HERMES_HEARTBEAT_S',
        'HERMES_DEBUG',
        'HERMES_BIND',
        'HERMES_WS_POLL_S',
        'HERMES_WEB_DIST',
        'HERMES_LOG_LEVEL',
        'HERMES_LOG_FORMAT',
        'HERMES_LOG_FILE',
        'HERMES_REPO',
        'HERMES_SSH_HOSTS',
        'HERMES_SSH_RESOURCES',
        'HERMES_AUTHORIZED_KEY',
        'HERMES_DEVSERVER_HOSTS',
        'HERMES_REPO_URL',
        'HERMES_DEVSERVER_INSTALL_CMD',
        'HERMES_DEVSERVER_SUBMIT_CMD',
        'HERMES_DEVSERVER_RECHECK_CMD',
        'DEXTER_KB_PY',
        'INVESTIGATIONS_DIR',
        'HERMES_PLAYBOOK_MODULES',
        'HERMES_SITE_MODULES',
        'HERMES_AGENT_MODULES',
        'HERMES_LOCAL_DIR',
    }

    assert required_vars.issubset(set(KNOWN_VARS.keys())), \
        f"Missing vars: {required_vars - set(KNOWN_VARS.keys())}"


def test_known_vars_has_dynamic_suffix_note():
    """KNOWN_VARS contains a note about dynamic HERMES_SSH_*_<host> suffixes."""
    from engine.config import KNOWN_VARS

    # Should have at least one key that mentions the dynamic suffixes
    dynamic_note_found = any(
        'HERMES_SSH_' in key and '<host>' in key
        for key in KNOWN_VARS.keys()
    )
    assert dynamic_note_found, "KNOWN_VARS should document dynamic HERMES_SSH_*_<host> suffixes"


def test_known_vars_all_have_descriptions():
    """All KNOWN_VARS entries have non-empty descriptions."""
    from engine.config import KNOWN_VARS

    for var, desc in KNOWN_VARS.items():
        assert isinstance(desc, str), f"{var} description must be a string"
        assert len(desc.strip()) > 0, f"{var} must have a non-empty description"


# --- validate_startup tests (Slice 3) ---

def test_validate_startup_accepts_clean_env():
    """validate_startup() succeeds on a clean environment."""
    from engine.config import validate_startup
    import tempfile

    # Clean env with valid HERMES_HOME
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        old_level = os.environ.pop('HERMES_LOG_LEVEL', None)
        old_format = os.environ.pop('HERMES_LOG_FORMAT', None)
        old_heartbeat = os.environ.pop('HERMES_HEARTBEAT_S', None)
        old_ws_poll = os.environ.pop('HERMES_WS_POLL_S', None)

        try:
            # Should not raise
            validate_startup()
        finally:
            os.environ.pop('HERMES_HOME', None)
            if old_level:
                os.environ['HERMES_LOG_LEVEL'] = old_level
            if old_format:
                os.environ['HERMES_LOG_FORMAT'] = old_format
            if old_heartbeat:
                os.environ['HERMES_HEARTBEAT_S'] = old_heartbeat
            if old_ws_poll:
                os.environ['HERMES_WS_POLL_S'] = old_ws_poll


def test_validate_startup_rejects_invalid_log_level():
    """validate_startup() rejects invalid HERMES_LOG_LEVEL with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_LOG_LEVEL'] = 'loud'

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup()

            # Should name the offending variable
            assert 'HERMES_LOG_LEVEL' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_LOG_LEVEL', None)


def test_validate_startup_rejects_invalid_log_format():
    """validate_startup() rejects invalid HERMES_LOG_FORMAT with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_LOG_FORMAT'] = 'xml'

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup()

            # Should name the offending variable
            assert 'HERMES_LOG_FORMAT' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_LOG_FORMAT', None)


def test_validate_startup_rejects_heartbeat_zero():
    """validate_startup() rejects HERMES_HEARTBEAT_S=0 with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_HEARTBEAT_S'] = '0'

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup()

            assert 'HERMES_HEARTBEAT_S' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_HEARTBEAT_S', None)


def test_validate_startup_rejects_heartbeat_negative():
    """validate_startup() rejects HERMES_HEARTBEAT_S=-1 with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_HEARTBEAT_S'] = '-1'

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup()

            assert 'HERMES_HEARTBEAT_S' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_HEARTBEAT_S', None)


def test_validate_startup_rejects_heartbeat_non_numeric():
    """validate_startup() rejects HERMES_HEARTBEAT_S=abc with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_HEARTBEAT_S'] = 'abc'

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup()

            assert 'HERMES_HEARTBEAT_S' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_HEARTBEAT_S', None)


def test_validate_startup_rejects_ws_poll_zero():
    """validate_startup() rejects HERMES_WS_POLL_S=0 with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_WS_POLL_S'] = '0'

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup()

            assert 'HERMES_WS_POLL_S' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_WS_POLL_S', None)


def test_validate_startup_rejects_ws_poll_negative():
    """validate_startup() rejects HERMES_WS_POLL_S=-1 with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_WS_POLL_S'] = '-1'

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup()

            assert 'HERMES_WS_POLL_S' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_WS_POLL_S', None)


def test_validate_startup_rejects_ws_poll_non_numeric():
    """validate_startup() rejects HERMES_WS_POLL_S=abc with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_WS_POLL_S'] = 'abc'

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup()

            assert 'HERMES_WS_POLL_S' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_WS_POLL_S', None)


def test_validate_startup_rejects_networked_mount():
    """validate_startup() rejects networked-mount HERMES_HOME with named ConfigError."""
    from engine.config import validate_startup, ConfigError
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Fake is_networked probe that says tmpdir is networked
        def fake_networked(path):
            return str(path).startswith(tmpdir)

        os.environ['HERMES_HOME'] = tmpdir

        try:
            with pytest.raises(ConfigError) as exc_info:
                validate_startup(is_networked=fake_networked)

            # Should mention HERMES_HOME (via resolve_home's error)
            assert 'HERMES_HOME' in str(exc_info.value)
        finally:
            os.environ.pop('HERMES_HOME', None)


def test_validate_startup_require_server_with_fastapi_installed():
    """validate_startup(require_server=True) succeeds when fastapi/uvicorn are importable."""
    from engine.config import validate_startup
    import tempfile

    # Check if fastapi is installed (skip if not)
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        pytest.skip("fastapi/uvicorn not installed")

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir

        try:
            # Should not raise
            validate_startup(require_server=True)
        finally:
            os.environ.pop('HERMES_HOME', None)


def test_validate_startup_require_server_missing_server_deps():
    """validate_startup(require_server=True) raises ConfigError with install hint when fastapi/uvicorn missing."""
    from engine.config import validate_startup, ConfigError
    import tempfile
    import sys

    # Temporarily hide fastapi and uvicorn from import
    hidden_modules = {}
    for mod in ['fastapi', 'uvicorn']:
        if mod in sys.modules:
            hidden_modules[mod] = sys.modules.pop(mod)

    # Mock the import to fail
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ['fastapi', 'uvicorn']:
            raise ImportError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = mock_import

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir

            try:
                with pytest.raises(ConfigError) as exc_info:
                    validate_startup(require_server=True)

                # Should have the install hint message
                assert "pip install -e '.[server]'" in str(exc_info.value)
            finally:
                os.environ.pop('HERMES_HOME', None)
    finally:
        # Restore import
        builtins.__import__ = real_import
        for mod, module in hidden_modules.items():
            sys.modules[mod] = module


def test_validate_startup_main_integration():
    """main() calls validate_startup on entry and returns clean nonzero on ConfigError."""
    from engine.cli import main
    import tempfile

    # Set up invalid config (bad log level)
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['HERMES_HOME'] = tmpdir
        os.environ['HERMES_LOG_LEVEL'] = 'INVALID'

        try:
            # main() with no args (prints help, but should fail on validate_startup first)
            exit_code = main([])

            # Should return nonzero (not raise)
            assert exit_code != 0
        finally:
            os.environ.pop('HERMES_HOME', None)
            os.environ.pop('HERMES_LOG_LEVEL', None)


# --- state_dir tests ---

def test_state_dir_lands_under_hermes_home(tmp_path, monkeypatch):
    """state_dir() creates the directory under HERMES_HOME."""
    from engine.config import state_dir

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    result = state_dir("scratch", "test-agent")

    assert result == tmp_path / "scratch" / "test-agent"
    assert result.is_dir()


def test_state_dir_mode_is_0700(tmp_path, monkeypatch):
    """state_dir() creates directories with owner-only (0700) permissions."""
    from engine.config import state_dir

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    result = state_dir("tmp")

    mode = result.stat().st_mode & 0o777
    assert mode == 0o700, f"Expected mode 0700, got {oct(mode)}"


def test_state_dir_idempotent(tmp_path, monkeypatch):
    """state_dir() is idempotent — calling it twice does not raise."""
    from engine.config import state_dir

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    first = state_dir("scratch", "codex")
    second = state_dir("scratch", "codex")

    assert first == second
    assert second.is_dir()


def test_state_dir_returns_path_object(tmp_path, monkeypatch):
    """state_dir() returns a Path object."""
    from pathlib import Path
    from engine.config import state_dir

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    result = state_dir("tmp")

    assert isinstance(result, Path)
