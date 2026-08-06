"""Configuration management for Hermes engine.

Resolves HERMES_HOME, manages env vars, and enforces safety constraints.
"""
import os
from pathlib import Path


class ConfigError(Exception):
    """Configuration validation error."""
    pass


def _default_networked_check(path: Path) -> bool:
    """Default check for networked/synced filesystems.

    Returns True if path appears to be on a networked mount.
    Checks HERMES_NETWORKED_PREFIXES env var (comma-separated) or common mounts.
    """
    path_str = str(path.resolve())

    # Read optional env denylist (empty by default)
    env_prefixes = os.environ.get('HERMES_NETWORKED_PREFIXES', '')
    networked_prefixes = [p.strip() for p in env_prefixes.split(',') if p.strip()]

    # Fallback: common networked/synced mount prefixes (no domain-specific paths; 
    if not networked_prefixes:
        networked_prefixes = [
            '/mnt/fuse',
            '/mnt/nfs',
        ]

    for prefix in networked_prefixes:
        if path_str.startswith(prefix):
            return True

    return False


def resolve_home(is_networked=None) -> Path:
    """Resolve HERMES_HOME from environment or default.

    Returns the absolute path to HERMES_HOME.
    Defaults to ~/.hermes if HERMES_HOME is unset.

    Args:
        is_networked: Optional callable (Path -> bool) to check if a path
                     is on a networked filesystem. Defaults to built-in check.

    Raises:
        ConfigError: If HERMES_HOME is on a networked/synced filesystem.
    """
    if is_networked is None:
        is_networked = _default_networked_check

    hermes_home_env = os.environ.get('HERMES_HOME')
    if hermes_home_env:
        home = Path(hermes_home_env).resolve()
    else:
        home = Path.home() / '.hermes'

    # Enforce networked-mount guard
    if is_networked(home):
        raise ConfigError(
            f"HERMES_HOME must not be on a networked or synced filesystem. "
            f"Refusing path: {home}. "
            f"SQLite queue.db requires local storage. "
            f"Please set HERMES_HOME to a local directory."
        )

    return home


def state_dir(*parts: str) -> Path:
    """Single canonical location for all Hermes-created runtime files and scratch data.

    Returns ``resolve_home().joinpath(*parts)``, creating the directory (and any
    parents) with owner-only permissions (0o700). This is the sole substitute for
    ``tempfile.gettempdir()`` and hardcoded ``/tmp`` paths: nothing Hermes creates
    must land outside the runtime root.

    Args:
        *parts: Path components to join under the runtime root.

    Returns:
        The created Path.
    """
    path = resolve_home().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def heartbeat_s() -> int:
    """Return HERMES_HEARTBEAT_S from env (default: 30)."""
    return int(os.environ.get('HERMES_HEARTBEAT_S', '30'))


def site() -> str:
    """Return HERMES_SITE from env (default: 'local')."""
    return os.environ.get('HERMES_SITE', 'local')


def agent() -> str:
    """Return HERMES_AGENT from env (default: 'claude')."""
    return os.environ.get('HERMES_AGENT', 'claude')


def bind() -> str:
    """Return HERMES_BIND from env (default: '127.0.0.1')."""
    return os.environ.get('HERMES_BIND', '127.0.0.1')


def ws_poll_s() -> float:
    """Return HERMES_WS_POLL_S from env as float (default: 1.0)."""
    return float(os.environ.get('HERMES_WS_POLL_S', '1.0'))


def web_dist() -> str:
    """Return HERMES_WEB_DIST from env (default: 'web/dist')."""
    return os.environ.get('HERMES_WEB_DIST', 'web/dist')


def log_level() -> str:
    """Return HERMES_LOG_LEVEL from env (default: INFO, or DEBUG if HERMES_DEBUG truthy).

    Explicit HERMES_LOG_LEVEL wins over HERMES_DEBUG.
    """
    level = os.environ.get('HERMES_LOG_LEVEL')
    if level is None:
        if os.environ.get('HERMES_DEBUG'):
            return 'DEBUG'
        return 'INFO'
    return level


def log_format() -> str:
    """Return HERMES_LOG_FORMAT from env (default: 'text')."""
    return os.environ.get('HERMES_LOG_FORMAT', 'text')


def log_file() -> str | None:
    """Return HERMES_LOG_FILE from env (default: None -> stderr)."""
    return os.environ.get('HERMES_LOG_FILE')


def debug() -> bool:
    """Return HERMES_DEBUG from env as bool (default: False).

    Truthy values: 1, true, True, TRUE, yes
    Falsy values: 0, false, False, FALSE, empty string, no, or unset
    """
    val = os.environ.get('HERMES_DEBUG', '')
    if not val:
        return False
    return val.lower() not in ('0', 'false', 'no', '')


def playbook_modules() -> list[str]:
    """Return HERMES_PLAYBOOK_MODULES from env as list of module paths (default: []).

    Parses comma-separated module paths, stripping whitespace.
    """
    val = os.environ.get('HERMES_PLAYBOOK_MODULES', '')
    if not val:
        return []
    return [m.strip() for m in val.split(',') if m.strip()]


def site_modules() -> list[str]:
    """Return HERMES_SITE_MODULES from env as list of module paths (default: []).

    Parses comma-separated module paths, stripping whitespace.
    """
    val = os.environ.get('HERMES_SITE_MODULES', '')
    if not val:
        return []
    return [m.strip() for m in val.split(',') if m.strip()]


def agent_modules() -> list[str]:
    """Return HERMES_AGENT_MODULES from env as list of module paths (default: []).

    Parses comma-separated module paths, stripping whitespace.
    """
    val = os.environ.get('HERMES_AGENT_MODULES', '')
    if not val:
        return []
    return [m.strip() for m in val.split(',') if m.strip()]


def local_dir() -> Path:
    """Return HERMES_LOCAL_DIR from env or default to resolve_home()/local.

    Returns the path for local adapter auto-discovery (does NOT verify existence).
    """
    val = os.environ.get('HERMES_LOCAL_DIR')
    if val:
        return Path(val)
    return resolve_home() / 'local'


def validate_startup(*, is_networked=None, require_server=False) -> None:
    """Validate startup preconditions.

    Runs the preconditions-to-running subset of checks and raises ConfigError
    on the first failure, with a message naming the offending variable.

    Args:
        is_networked: Optional callable (Path -> bool) to check if a path
                     is on a networked filesystem. Passed to resolve_home().
        require_server: If True, verify fastapi/uvicorn are importable.

    Raises:
        ConfigError: If any validation check fails, with a message naming
                    the offending variable.
    """
    # 1. resolve_home() succeeds and passes networked-FS guard
    resolve_home(is_networked=is_networked)

    # 2. log_level() is valid
    level = log_level()
    valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR'}
    if level not in valid_levels:
        raise ConfigError(
            f"HERMES_LOG_LEVEL must be one of {valid_levels}, got: {level!r}"
        )

    # 3. log_format() is valid
    format_val = log_format()
    valid_formats = {'text', 'json'}
    if format_val not in valid_formats:
        raise ConfigError(
            f"HERMES_LOG_FORMAT must be one of {valid_formats}, got: {format_val!r}"
        )

    # 4. heartbeat_s() parses as positive number
    heartbeat_raw = os.environ.get('HERMES_HEARTBEAT_S', '30')
    try:
        heartbeat_val = int(heartbeat_raw)
        if heartbeat_val <= 0:
            raise ConfigError(
                f"HERMES_HEARTBEAT_S must be a positive integer, got: {heartbeat_raw!r}"
            )
    except ValueError:
        raise ConfigError(
            f"HERMES_HEARTBEAT_S must be a valid integer, got: {heartbeat_raw!r}"
        )

    # 5. ws_poll_s() parses as positive number
    ws_poll_raw = os.environ.get('HERMES_WS_POLL_S', '1.0')
    try:
        ws_poll_val = float(ws_poll_raw)
        if ws_poll_val <= 0:
            raise ConfigError(
                f"HERMES_WS_POLL_S must be a positive number, got: {ws_poll_raw!r}"
            )
    except ValueError:
        raise ConfigError(
            f"HERMES_WS_POLL_S must be a valid number, got: {ws_poll_raw!r}"
        )

    # 6. When require_server=True: fastapi/uvicorn importable
    if require_server:
        try:
            import fastapi  # noqa: F401
            import uvicorn  # noqa: F401
        except ImportError:
            raise ConfigError(
                "Error: server dependencies not installed. Run: pip install -e '.[server]'"
            )


KNOWN_VARS: dict[str, str] = {
    'HERMES_HOME': 'Runtime-data root (queue.db, api_token, workspaces, guard shims, logs). Refused on networked/synced mount.',
    'HERMES_NETWORKED_PREFIXES': 'Comma-separated mount-prefix denylist for the networked-FS guard.',
    'HERMES_SITE': 'Default site name when --site omitted.',
    'HERMES_AGENT': 'Worker-runtime adapter to load.',
    'HERMES_HEARTBEAT_S': 'Crew-health / lease-renew heartbeat + no-progress window (seconds).',
    'HERMES_DEBUG': 'Print tracebacks on CLI error (subsumed by HERMES_LOG_LEVEL).',
    'HERMES_BIND': 'API bind address; non-loopback gates all GETs on the token.',
    'HERMES_WS_POLL_S': 'Websocket event-poll interval (seconds).',
    'HERMES_WEB_DIST': 'SPA dist/ directory to serve.',
    'HERMES_LOG_LEVEL': 'Operational log level (DEBUG/INFO/WARNING/ERROR).',
    'HERMES_LOG_FORMAT': 'Log formatter type (text/json).',
    'HERMES_LOG_FILE': 'Log file path (unset -> stderr).',
    'HERMES_REPO': 'Source repo the local site worktrees from.',
    'HERMES_SSH_HOSTS': 'Comma-separated host list for the ssh site.',
    'HERMES_SSH_{PORT,USER,HOSTNAME,IDENTITY,RESOURCES}_<host>': 'Dynamic per-host ssh config suffixes (port, login user, address, private-key path, resources JSON).',
    'HERMES_SSH_RESOURCES': 'Worker-image resource label (informational).',
    'HERMES_AUTHORIZED_KEY': 'Throwaway pubkey injected into a worker authorized_keys (secret).',
    'HERMES_DEVSERVER_HOSTS': 'Devserver host list.',
    'HERMES_REPO_URL': 'Repo URL the devserver site checks out.',
    'HERMES_DEVSERVER_INSTALL_CMD': 'Command to install claude/dexter on a devserver.',
    'HERMES_DEVSERVER_SUBMIT_CMD': 'Publish-only submit command (never lands).',
    'HERMES_DEVSERVER_RECHECK_CMD': 'CI/repro re-check command for verify.',
    'DEXTER_KB_PY': 'Path to dexter kb.py for banking learnings (master-side).',
    'INVESTIGATIONS_DIR': 'Dexter runtime-data dir for banked learnings.',
    'HERMES_PLAYBOOK_MODULES': 'Comma-separated custom playbook module paths to import for adapter registration.',
    'HERMES_SITE_MODULES': 'Comma-separated custom site module paths to import for adapter registration.',
    'HERMES_AGENT_MODULES': 'Comma-separated custom agent module paths to import for adapter registration.',
    'HERMES_LOCAL_DIR': 'Directory for zero-config local adapter auto-discovery (default: HERMES_HOME/local).',
    'HERMES_TRACE_MAX_MB': 'Largest worker trace captured per attempt, in MB (default: 50). A trace over this is dropped, not truncated.',
}
