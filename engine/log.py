"""Operational diagnostics logging (stdlib-only).

Provides structured logging layered beside the events domain feed.
Logging is for process diagnostics; events are the queryable audit trail.

API:
- get_logger(name) -> Logger: namespaced child of root 'hermes' logger
- configure(level=None, fmt=None, file=None): idempotent root config
- bind(**fields): contextmanager for run_id/ticket_id/host injection
- redact(mapping): return copy with secret keys masked
"""
import contextvars
import json
import logging
import os
import sys
from typing import Any


_configured = False
_bound_fields = contextvars.ContextVar("log_bound_fields", default={})


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child of the root hermes logger.

    Never configures handlers (that's configure()'s job).

    Args:
        name: Module name (e.g., "dispatch", "transport")

    Returns:
        Logger instance under hermes.<name>
    """
    return logging.getLogger(f"hermes.{name}")


def configure(
    *,
    level: str | None = None,
    fmt: str | None = None,
    file: str | None = None,
) -> None:
    """Configure the root hermes logger (idempotent, one-time setup).

    Reads env defaults when args are None:
    - HERMES_LOG_LEVEL (default: INFO, or DEBUG if HERMES_DEBUG truthy)
    - HERMES_LOG_FORMAT (default: text; values: text|json)
    - HERMES_LOG_FILE (default: unset -> stderr)

    Installs exactly one handler even on repeated calls.

    Args:
        level: Log level name (DEBUG|INFO|WARNING|ERROR)
        fmt: Formatter type (text|json)
        file: Log file path (None -> stderr)
    """
    global _configured

    # Get root hermes logger
    logger = logging.getLogger("hermes")

    # Idempotent guard: only configure once, but check if handler is still valid
    if _configured:
        # Check if existing handler is still usable
        if logger.handlers:
            handler = logger.handlers[0]
            try:
                # Try to check if stream is open (for StreamHandler)
                if hasattr(handler, 'stream') and hasattr(handler.stream, 'closed'):
                    if handler.stream.closed:
                        # Stream is closed, need to reconfigure
                        logger.handlers.clear()
                        _configured = False
                    else:
                        return
                else:
                    return
            except Exception:
                # If we can't check, assume it's fine
                return
        else:
            return

    _configured = True

    # Resolve level from args -> env -> defaults
    if level is None:
        level = os.environ.get("HERMES_LOG_LEVEL")
        if level is None:
            # HERMES_DEBUG=1 -> DEBUG, but explicit HERMES_LOG_LEVEL wins
            if os.environ.get("HERMES_DEBUG"):
                level = "DEBUG"
            else:
                level = "INFO"

    # Resolve format
    if fmt is None:
        fmt = os.environ.get("HERMES_LOG_FORMAT", "text")

    # Resolve file
    if file is None:
        file = os.environ.get("HERMES_LOG_FILE")

    # Set level on the logger
    logger.setLevel(getattr(logging, level.upper()))

    # Install exactly one handler
    if file:
        handler = logging.FileHandler(file)
    else:
        handler = logging.StreamHandler(sys.stderr)

    # Select formatter
    if fmt == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    handler.setFormatter(formatter)

    # Add filter to inject bound fields
    handler.addFilter(BoundFieldsFilter())

    logger.addHandler(handler)


class BoundFieldsFilter(logging.Filter):
    """Inject bound context fields into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        fields = _bound_fields.get()
        for key, value in fields.items():
            setattr(record, key, value)
        return True


class TextFormatter(logging.Formatter):
    """Text formatter: <ts> <level> <name> [run_id=... ticket_id=... host=...] message"""

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")
        level = record.levelname
        name = record.name
        msg = record.getMessage()

        # Build bound fields section
        fields = []
        for key in ("run_id", "ticket_id", "host"):
            value = getattr(record, key, None)
            if value is not None:
                fields.append(f"{key}={value}")

        if fields:
            fields_str = " [" + " ".join(fields) + "]"
        else:
            fields_str = ""

        return f"{ts} {level} {name}{fields_str} {msg}"


class JSONFormatter(logging.Formatter):
    """JSON formatter: one object per line with ts, level, logger, msg, bound fields, extra."""

    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Add bound fields
        for key in ("run_id", "ticket_id", "host"):
            value = getattr(record, key, None)
            if value is not None:
                obj[key] = value

        # Add extra fields (anything not in standard LogRecord attributes)
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName", "levelname",
            "levelno", "lineno", "module", "msecs", "message", "pathname", "process",
            "processName", "relativeCreated", "thread", "threadName", "exc_info",
            "exc_text", "stack_info", "run_id", "ticket_id", "host"
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                obj[key] = value

        return json.dumps(obj, separators=(",", ":"))


class bind:
    """Context manager to bind run_id/ticket_id/host to all logs in scope.

    Usage:
        with bind(run_id="r1", host="h1"):
            logger.info("processing")  # logs will include run_id=r1 host=h1
    """

    def __init__(self, **fields):
        self.fields = fields
        self.token = None

    def __enter__(self):
        # Merge with any existing bound fields
        current = _bound_fields.get()
        new_fields = {**current, **self.fields}
        self.token = _bound_fields.set(new_fields)
        return self

    def __exit__(self, *args):
        _bound_fields.reset(self.token)


def redact(mapping: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of mapping with secret keys replaced by '***'.

    Secret keys: token, api_token, authorized_key, identity

    Args:
        mapping: Dict to redact

    Returns:
        New dict with secrets masked
    """
    secret_keys = {"token", "api_token", "authorized_key", "identity"}
    result = {}
    for key, value in mapping.items():
        if key in secret_keys:
            result[key] = "***"
        else:
            result[key] = value
    return result
