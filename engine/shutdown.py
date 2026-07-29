"""Graceful shutdown support via SIGTERM/SIGINT (stdlib-only).

Provides a process-global threading.Event that signal handlers set, allowing
long-running loops to check and exit cleanly at safe boundaries.
"""
import signal
import threading

from engine import log


# Module-global stop event. Created once at import, never reassigned.
# Handlers set it; loops check it at safe boundaries.
stop_event = threading.Event()


def install_handlers() -> None:
    """Install SIGTERM and SIGINT handlers that set the global stop_event.

    The handler does nothing but set the event (no I/O in signal handler).
    Call this ONCE from the main thread in cmd_run and worker cmd_serve --host.
    Do NOT call from cmd_serve_api (uvicorn owns SIGTERM there).
    """
    def handler(signum, frame):
        # No I/O in a signal handler - just set the flag
        stop_event.set()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def log_graceful_shutdown() -> None:
    """Log a graceful-shutdown INFO line via engine.log.

    Called by the main loop after it has exited cleanly and run the final
    heartbeat_sweep, just before closing the DB and exiting 0.
    """
    logger = log.get_logger("shutdown")
    logger.info("Graceful shutdown complete")
