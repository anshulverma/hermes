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
}
