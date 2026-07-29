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
