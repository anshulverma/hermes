"""
server.auth — bearer-token authentication (DESIGN §10).

Token lifecycle:
- load_or_create_token: generate a strong random token via secrets.token_urlsafe
  if absent, write 0600, return it (idempotent).
- rotate_token: overwrite with a new one.
- read_token: read current, or None.
"""
import os
import secrets
from pathlib import Path


def load_or_create_token(home: Path) -> str:
    """Load existing token or create a new one at $HERMES_HOME/api_token (0600).

    Idempotent: if the token file already exists, just reads and returns it.
    If absent, generates a strong random token via secrets.token_urlsafe(32),
    writes it with mode 0600, and returns it.

    Args:
        home: HERMES_HOME directory

    Returns:
        The bearer token as a string
    """
    token_path = home / "api_token"

    if token_path.exists():
        return token_path.read_text().strip()

    # Generate a new token
    token = secrets.token_urlsafe(32)

    # Write with mode 0600
    token_path.write_text(token)
    os.chmod(token_path, 0o600)

    return token


def rotate_token(home: Path) -> str:
    """Generate and write a new token, overwriting any existing one.

    Args:
        home: HERMES_HOME directory

    Returns:
        The new bearer token as a string
    """
    token_path = home / "api_token"

    # Generate a new token
    token = secrets.token_urlsafe(32)

    # Write with mode 0600 (overwrite existing)
    token_path.write_text(token)
    os.chmod(token_path, 0o600)

    return token


def read_token(home: Path) -> str | None:
    """Read the current token, or None if not found.

    Args:
        home: HERMES_HOME directory

    Returns:
        The bearer token as a string, or None if file doesn't exist
    """
    token_path = home / "api_token"

    if not token_path.exists():
        return None

    return token_path.read_text().strip()
