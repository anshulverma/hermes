"""FastAPI control plane server with bearer-token auth, WebSocket live events, and SPA serving with token injection on loopback."""
import asyncio
import hashlib
import json
import math
import os
import re
import secrets
import stat
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Annotated, Literal, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware

from engine import config
from engine.db.migrate import connect
from engine.models import Reduction
from engine.queue import (
    TERMINAL_RUN_STATES,
    apply_run_action,
    load_run,
    phase_ticket_counts,
    set_run_state,
)
from engine import log
from engine import trace
from server import trace_view
from server.auth import load_or_create_token


# Security scheme for bearer token
security = HTTPBearer(auto_error=False)


def is_loopback(bind: str | None) -> bool:
    """Check if bind address is loopback."""
    if bind is None:
        return True
    return bind in ("127.0.0.1", "localhost", "::1")


# Playbook-owned views (spec §4): two optional duck-typed methods on a playbook
# object, never on the Playbook Protocol, so a playbook without them is simply
# a playbook with no view. The kill switch is one env var so an operator binding
# past loopback can stop executing playbook-authored JS in the browser (spec §9).
VIEWS_ENV = "HERMES_PLAYBOOK_VIEWS"

# All-or-nothing, which is what §9 demands: no value half-disables anything.
# A set rather than the literal "0" because an operator reaching for a kill
# switch writes `false` or `off` as readily as `0`, and getting the feature
# fully ENABLED for their trouble is a silent footgun. The empty string is NOT
# here: `-e HERMES_PLAYBOOK_VIEWS` with nothing behind it is a variable an
# operator did not set, and must read as unset does.
VIEWS_OFF = frozenset({"0", "false", "no", "off"})

# An artifact is read whole into a JSON response, so the read is bounded twice:
# the path must name a regular file (a FIFO blocks the worker thread forever;
# /dev/zero is a MemoryError), and the read stops here. A playbook's artifact is
# typically an operator-chosen file of unbounded size, so "large" needs no
# malice and no bug. Over the cap the response says so rather than lying by
# omission.
ARTIFACT_MAX_CHARS = 2 * 1024 * 1024

# The per-run directories a playbook view may read a file from. The view names
# each file itself (its `view_data` emits every `path`); the server knows these
# directory names and no file names. A second kind of per-run file is one more
# entry here.
RUN_FILE_DIRS = ("doc", "images")

# An image is served as raw bytes, whole or not at all: over this it is a 413,
# never a truncated picture. Equal to the playbook side's own image cap.
RUN_FILE_MAX_BYTES = 2 * 1024 * 1024

# The two image types a view may show, by suffix. An SVG is worker-written
# markup served from this origin, so it goes out under a CSP that sandboxes it
# and allows no script, no fetch and no navigation, and as an attachment, so
# opened directly it downloads instead of rendering. An <img> ignores both.
_IMAGE_TYPES = {".png": "image/png", ".svg": "image/svg+xml"}
_IMAGE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "Cache-Control": "no-store",
}

# A file name inside one of those directories: no leading dot (so a temp file
# being written is never served), no separator, no NUL, bounded.
_RUN_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

# A metrics chart never needs more bars than a day of minutes. Past this the
# bucket widens instead, so a run row with a bad created_at (or ?bucket_s=1 on
# a long run) cannot ask for millions of buckets.
METRICS_MAX_BUCKETS = 1440


def _image_magic_ok(data: bytes, suffix: str) -> bool:
    """PNG's signature, or an SVG whose first non-blank bytes (after a BOM) open it."""
    if suffix == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    text = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
    return text.lstrip().startswith((b"<svg", b"<?xml"))


def _image_response(fd: int, path: str, sha256: str = "") -> Response:
    """The image ``fd`` holds, as raw bytes under the image headers. Closes ``fd``.

    A non-empty ``sha256`` names the exact bytes the caller wants (the ones its
    playbook checked): anything else in the file now is a 404, so a later
    writer cannot swap the picture under an earlier reference.
    """
    name = path.split("/")[1]  # already held to _RUN_FILE_NAME: no quote, no separator
    suffix = Path(name).suffix
    too_big = HTTPException(status_code=413, detail=f"{path} is over {RUN_FILE_MAX_BYTES} bytes")
    try:
        with open(fd, "rb") as handle:
            if os.fstat(handle.fileno()).st_size > RUN_FILE_MAX_BYTES:
                raise too_big
            data = handle.read(RUN_FILE_MAX_BYTES + 1)
    except OSError:
        raise HTTPException(status_code=404, detail=f"{path} is not readable")
    if len(data) > RUN_FILE_MAX_BYTES:  # grew between the fstat and the read
        raise too_big
    if not _image_magic_ok(data, suffix):
        raise HTTPException(status_code=404, detail=f"{path} is not a {suffix[1:]} image")
    if sha256 and hashlib.sha256(data).hexdigest() != sha256:
        raise HTTPException(status_code=404, detail=f"{path} is not the image that was checked")
    return Response(
        content=data,
        media_type=_IMAGE_TYPES[suffix],
        headers={**_IMAGE_HEADERS, "Content-Disposition": f'attachment; filename="{name}"'},
    )


def _open_run_file(home: Path, run_id: str, path: str) -> int:
    """A read-only fd on the file ``path`` names in ``home/runs/<run_id>/``, or an HTTPException.

    ``path`` must be exactly ``<dir>/<name>`` with ``dir`` in RUN_FILE_DIRS
    (400 otherwise: empty, absolute, ``..``, NUL, a backslash, three parts).
    Then it must be a regular file reached without following a symlink at any
    level below ``runs/`` (404 otherwise). Walked one directory fd at a time,
    each opened ``O_NOFOLLOW`` relative to the last, because the run directory
    is worker-written: a path checked and then opened leaves a window to swap
    ``doc/`` for a symlink between the two. ``O_NONBLOCK`` keeps the open from
    hanging on a FIFO, and ``fstat`` refuses one, a device or a directory.
    Built only from a validated run id and this process's own home, the way
    ``engine.trace.trace_path`` builds a trace path -- never from a path a
    reduction recorded.
    """
    if not trace._RUN_ID_OK.match(run_id):
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    parts = path.split("/")
    if (
        len(parts) != 2
        or parts[0] not in RUN_FILE_DIRS
        or not _RUN_FILE_NAME.fullmatch(parts[1])
    ):
        raise HTTPException(
            status_code=400,
            detail=f"path must be <dir>/<name> with dir one of {list(RUN_FILE_DIRS)}, "
                   f"not {path!r}",
        )
    missing = HTTPException(status_code=404, detail=f"Run {run_id!r} has no {path}")
    below = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    dirs: list[int] = []
    try:
        dirs.append(os.open((home / "runs").resolve(), os.O_RDONLY | os.O_DIRECTORY))
        dirs.append(os.open(run_id, below, dir_fd=dirs[-1]))
        dirs.append(os.open(parts[0], below, dir_fd=dirs[-1]))
        fd = os.open(parts[1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirs[-1])
    except (OSError, RuntimeError):
        raise missing
    finally:
        for d in dirs:
            os.close(d)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise missing
    return fd


def view_playbook(name: str):
    """The registered playbook behind ``name``'s view, or None if there is none.

    One function so the four call sites cannot disagree about what "has a view"
    means. None covers every way a view can be absent: the kill switch, a name
    that is not in the registry, a playbook without the seam, a seam whose built
    asset is not on disk, and a seam that raises or hands back something that is
    not a path.

    The name is a registry key and never a path component, which is the whole
    traversal defence: a name carrying ``../`` misses the registry and gets the
    same None as any other unknown name.
    """
    if (os.environ.get(VIEWS_ENV) or "").strip().casefold() in VIEWS_OFF:
        return None
    from engine import playbook as playbook_module
    try:
        obj = playbook_module.load(name)
    except KeyError:
        return None
    if not callable(getattr(obj, "view_asset", None)):
        return None
    if not callable(getattr(obj, "view_data", None)):
        return None
    # A BROKEN seam is an absent seam. This is the one call into playbook code
    # made from `GET /api/runs/{id}`, a core route that could not 500 before the
    # seam existed -- a view_asset that raises, or returns something that is not
    # a path, must cost that run's page nothing.
    try:
        asset = obj.view_asset()
        if asset is None or not Path(asset).exists():
            return None
    except Exception:
        return None
    return obj


# A subject is a list-row heading, so it is one line and bounded even when the
# text it is derived from is a multi-kilobyte prompt.
SUBJECT_MAX_CHARS = 200


def ticket_subject(payload: dict[str, Any]) -> str:
    """The one-line heading for a ticket.

    An explicit ``title`` is what the playbook wants shown. Payloads that do not
    carry one fall back to the goal, whose first line is the closest thing to a
    heading it has; either way the result is a single bounded line.
    """
    for key in ("title", "goal", "subject"):
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        line = value.strip().splitlines()[0].strip() if value.strip() else ""
        if not line:
            continue
        if len(line) > SUBJECT_MAX_CHARS:
            line = line[: SUBJECT_MAX_CHARS - 1].rstrip() + "…"
        return line
    return "—"


def create_app(bind: str | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        bind: Bind address (default from HERMES_BIND or 127.0.0.1).
              Used to determine GET-gating and token injection.
    """
    # Validate startup config (including server dependencies)
    config.validate_startup(require_server=True)

    # Configure logging once at entry
    log.configure()

    if bind is None:
        bind = config.bind()

    # Load or create the bearer token
    home = config.resolve_home()
    app_token = load_or_create_token(home)
    loopback = is_loopback(bind)

    # Log startup info (token location, never the value)
    logger = log.get_logger("server")
    token_path = home / "api_token"
    logger.info(f"Server starting: bind={bind}, home={home}, token_file={token_path}")

    # Register real adapters (playbooks, sites, agents) once at startup
    # Import built-in adapters
    import sites.local.site  # noqa: F401
    import sites.devserver.site  # noqa: F401
    import sites.fan  # noqa: F401
    import playbooks.dexter  # noqa: F401
    import playbooks.research  # noqa: F401
    import agents.claude  # noqa: F401

    # Import custom adapter modules from env vars + local/ dir
    from engine.cli import _import_registration_modules
    try:
        _import_registration_modules()
    except Exception as e:
        logger.warning(f"Failed to import custom registration modules: {e}")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager for startup/shutdown logging."""
        logger.info("API server started")
        yield
        logger.info("API server stopped")

    app = FastAPI(title="Hermes Control Plane", version="0.1.0", lifespan=lifespan)

    # Compress responses (the SPA JS bundle + JSON) so page loads are fast over a network.
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Request logging middleware (strip query strings to avoid logging tokens)
    @app.middleware("http")
    async def log_requests(request, call_next):
        """Log requests with query strings stripped."""
        req_logger = log.get_logger("server.request")
        # Log method and path only (no query string)
        req_logger.debug(f"{request.method} {request.url.path}")
        response = await call_next(request)
        return response

    # Auth dependency: validates bearer token from header or query param
    def require_auth(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
        token: str | None = Query(None)
    ) -> None:
        """Validate bearer token (from Authorization header or ?token= query param).

        Raises 401 if token is missing or invalid.
        """
        # Try header first, then query param
        provided_token = None
        if credentials:
            provided_token = credentials.credentials
        elif token:
            provided_token = token

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(provided_token or "", app_token or ""):
            raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    # Auth dependency for GET endpoints: only gate on non-loopback
    def require_auth_read(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
        token: str | None = Query(None)
    ) -> None:
        """Validate bearer token for GET endpoints (only on non-loopback)."""
        if not loopback:
            require_auth(credentials, token)

    @app.get("/api/health")
    def health(_: None = Depends(require_auth_read)) -> dict[str, Any]:
        """Health check endpoint.

        Returns status, version, and resolved HERMES_HOME.
        """
        home = config.resolve_home()
        return {
            "status": "ok",
            "version": "0.1.0",
            "home": str(home),
        }

    @app.get("/api/runs")
    def list_runs(_: None = Depends(require_auth_read)) -> list[dict[str, Any]]:
        """List all runs with ticket counts by state.

        Returns a list of runs, each with per-state ticket counts.
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            rows = conn.execute(
                """SELECT id, playbook, site, state, phase, base_ref, created_at
                   FROM runs ORDER BY created_at DESC"""
            ).fetchall()

            runs = []
            for row in rows:
                run_id, playbook, site, state, phase, base_ref, created_at = row

                # Get ticket counts by state
                ticket_rows = conn.execute(
                    """SELECT state, COUNT(*) FROM tickets
                       WHERE run_id=? GROUP BY state""",
                    (run_id,),
                ).fetchall()
                tickets = {state: count for state, count in ticket_rows}

                runs.append({
                    "id": run_id,
                    "playbook": playbook,
                    "site": site,
                    "state": state,
                    "phase": phase,
                    "base_ref": base_ref,
                    "created_at": created_at,
                    "tickets": tickets,
                })

            return runs
        finally:
            conn.close()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, _: None = Depends(require_auth_read)) -> dict[str, Any]:
        """Get a single run by ID with phase ticket counts.

        Returns run details including per-state ticket counts and
        per-phase ticket counts (as an array in playbook phase order).
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Check if run exists and get basic info
            row = conn.execute(
                """SELECT id, playbook, site, state, phase, base_ref,
                          config_json, created_at, updated_at
                   FROM runs WHERE id=?""",
                (run_id,),
            ).fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

            (rid, playbook_name, site, state, current_phase, base_ref,
             config_json, created_at, updated_at) = row

            # Get ticket counts by state
            ticket_rows = conn.execute(
                """SELECT state, COUNT(*) FROM tickets
                   WHERE run_id=? GROUP BY state""",
                (run_id,),
            ).fetchall()
            tickets = {state: count for state, count in ticket_rows}

            # The rail: phases that minted tickets, in the order they first
            # did, then the declared phases not reached yet.
            from engine import playbook as playbook_module

            minted = [r[0] for r in conn.execute(
                """SELECT phase FROM tickets
                   WHERE run_id=? GROUP BY phase ORDER BY MIN(rowid)""",
                (run_id,),
            ).fetchall()]
            try:
                declared = list(playbook_module.load(playbook_name).phases)
            except KeyError:
                declared = []  # unregistered: the tickets are all we have
            # No phase yet: the whole plan is ahead. A phase the plan does not
            # name: the run has left the declared list behind.
            if current_phase in declared:
                ahead = declared.index(current_phase)
            else:
                ahead = len(declared) if current_phase else 0
            phase_names = minted + [p for p in declared[ahead:] if p not in minted]
            # The run sets its phase before seeding it, so it can be current
            # with no tickets yet.
            if current_phase and current_phase not in phase_names:
                phase_names.append(current_phase)

            phases = [
                {
                    "name": name,
                    "counts": phase_ticket_counts(conn, run_id, name),
                    "current": name == current_phase,
                }
                for name in phase_names
            ]

            return {
                "id": rid,
                "playbook": playbook_name,
                "site": site,
                "state": state,
                "phase": current_phase,
                "base_ref": base_ref,
                "config": json.loads(config_json),
                "created_at": created_at,
                "updated_at": updated_at,
                "tickets": tickets,
                "phases": phases,
                "has_view": view_playbook(playbook_name) is not None,
            }
        finally:
            conn.close()

    @app.get("/api/runs/{run_id}/tickets")
    def get_tickets(
        run_id: str,
        state: str | None = None,
        phase: str | None = None,
        resource: str | None = None,
        host: str | None = None,
        search: str | None = None,
        _: None = Depends(require_auth_read)
    ) -> list[dict[str, Any]]:
        """Get tickets for a run with optional filters.

        Query params (all optional, combine with AND):
        - state: filter by ticket state
        - phase: filter by phase
        - resource: filter by resource_req
        - host: filter by worker_host
        - search: substring match on id/subject

        Returns tickets with: id, run_id, state, phase, subject, resource_req,
        host, attempts, elapsed_s, priority.

        ``attempts`` is how many attempts the ticket actually recorded, counted
        in one grouped join rather than a query per ticket. The ``attempts``
        column on the ticket row is the infra-retry budget, which stays at zero
        for a ticket that ran once and succeeded, so it is not what to report.
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Verify run exists
            run_exists = conn.execute(
                "SELECT 1 FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if run_exists is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

            # Build query with filters
            query = """
                SELECT t.id, t.run_id, t.state, t.phase, t.resource_req, t.worker_host,
                       COALESCE(a.attempt_count, 0), t.priority, t.payload_json,
                       t.updated_at
                FROM tickets t
                LEFT JOIN (
                    SELECT ticket_id, COUNT(*) AS attempt_count
                    FROM attempts GROUP BY ticket_id
                ) a ON a.ticket_id = t.id
                WHERE t.run_id=?
            """
            params: list[Any] = [run_id]

            if state:
                query += " AND t.state=?"
                params.append(state)
            if phase:
                query += " AND t.phase=?"
                params.append(phase)
            if resource:
                query += " AND t.resource_req=?"
                params.append(resource)
            if host:
                query += " AND t.worker_host=?"
                params.append(host)
            if search:
                query += " AND (t.id LIKE ? OR t.payload_json LIKE ?)"
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])

            # p0 is highest priority (lowest number first), matching claim order.
            # Within a priority, seed order: ids carry unpadded counters, so
            # sorting on t.id would put solve-10 before solve-2.
            query += " ORDER BY t.priority ASC, t.rowid"

            rows = conn.execute(query, params).fetchall()

            # Build response
            import time
            now = time.time()
            tickets = []
            for row in rows:
                (
                    ticket_id, ticket_run_id, ticket_state, ticket_phase,
                    resource_req, worker_host, attempts, priority,
                    payload_json, updated_at
                ) = row

                payload = json.loads(payload_json)
                subject = ticket_subject(payload)

                # Compute elapsed_s
                elapsed_s = int(now - updated_at) if updated_at else 0

                tickets.append({
                    "id": ticket_id,
                    "run_id": ticket_run_id,
                    "state": ticket_state,
                    "phase": ticket_phase,
                    "subject": subject,
                    "resource_req": resource_req,
                    "host": worker_host,
                    "attempts": attempts,
                    "elapsed_s": elapsed_s,
                    "priority": priority,
                })

            return tickets
        finally:
            conn.close()

    def _available_actions(state: str, reduction_id: Optional[int]) -> list[str]:
        """Derive available operator actions for a ticket.

        Purely ticket-scoped: requeue/retry stay available even when the run has
        finished, because those reopen the run rather than stranding the ticket.
        """
        if state == "needs_human":
            if reduction_id is None:
                return ["requeue", "reprioritize", "abandon"]
            else:
                return ["accept_reduction", "reject_reduction", "abandon"]
        elif state == "failed":
            return ["retry"]
        elif state == "queued":
            return ["reprioritize", "abandon"]
        elif state in ("dispatched", "running", "reducing"):
            return ["abandon"]
        elif state == "parked":
            return ["reprioritize", "abandon"]
        elif state == "done":
            return []
        else:
            return []

    @app.get("/api/tickets/{ticket_id:path}")
    def get_ticket_detail(ticket_id: str, _: None = Depends(require_auth_read)) -> dict[str, Any]:
        """Get full ticket detail.

        Returns:
        - ticket: all ticket fields including parsed subject and reduction_id
        - payload: parsed payload_json (GoalEnvelope)
        - result: strict latest result (max id attempt) or null
        - attempt_timeline: all attempts ordered oldest→newest
        - evidence: non-null result_refs as {attempt, ref}
        - finding: the ticket's latest banked finding doc or null
        - answer: the finding's prose answer when it carries one, else null
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Get ticket
            ticket_row = conn.execute(
                """SELECT id, run_id, phase, state, resource_req, priority,
                          worker_host, reduction_id, payload_json, created_at, updated_at
                   FROM tickets WHERE id=?""",
                (ticket_id,),
            ).fetchone()

            if ticket_row is None:
                raise HTTPException(status_code=404, detail=f"Ticket {ticket_id!r} not found")

            (
                tid, run_id, phase, state, resource_req, priority,
                worker_host, reduction_id, payload_json, created_at, updated_at
            ) = ticket_row

            # The owning run's state gates which actions can still do anything.
            run_state_row = conn.execute(
                "SELECT state FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            run_state = run_state_row[0] if run_state_row else None

            # Parse payload
            payload = json.loads(payload_json)
            subject = ticket_subject(payload)

            # Get all attempts (ordered by id for timeline)
            attempt_rows = conn.execute(
                """SELECT id, attempt, host, outcome, termination_reason,
                          started_at, ended_at, result_ref, error_summary, error_detail
                   FROM attempts WHERE ticket_id=? ORDER BY id""",
                (ticket_id,),
            ).fetchall()

            # Build ticket object. ``attempts`` is how many attempts were
            # recorded — the ticket row's own column is the infra-retry budget,
            # which stays at zero for a ticket that ran once and succeeded.
            ticket = {
                "id": tid,
                "run_id": run_id,
                "phase": phase,
                "state": state,
                "resource_req": resource_req,
                "priority": priority,
                "attempts": len(attempt_rows),
                "host": worker_host,
                "reduction_id": reduction_id,
                "subject": subject,
                "created_at": created_at,
                "updated_at": updated_at,
            }

            # Build attempt_timeline
            attempt_timeline = []
            for row in attempt_rows:
                (
                    attempt_id, attempt_num, host, outcome, term_reason,
                    started_at, ended_at, result_ref, error_summary, error_detail
                ) = row
                attempt_timeline.append({
                    "attempt": attempt_num,
                    "host": host,
                    "outcome": outcome,
                    "termination_reason": term_reason,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "result_ref": result_ref,
                    "error_summary": error_summary,
                    "detail": error_detail,
                })

            # Derive strict latest result (max id attempt)
            result = None
            if attempt_rows:
                latest = attempt_rows[-1]  # Last in id-ordered list
                (
                    _, _, _, outcome, term_reason,
                    started_at, ended_at, result_ref, error_summary, error_detail
                ) = latest
                result = {
                    "outcome": outcome,
                    "termination_reason": term_reason,
                    "result_ref": result_ref,
                    "error_summary": error_summary,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "detail": error_detail,
                }

            # Build evidence (non-null result_refs). ``attempt_id`` is the
            # attempts row, which is what a captured trace is named for;
            # ``trace_bytes`` is non-null only when that trace is actually on
            # disk, so the UI can offer to open it instead of guessing.
            evidence = []
            for i, row in enumerate(attempt_rows):
                attempt_id = row[0]
                attempt_num = row[1]
                result_ref = row[7]  # result_ref column
                if result_ref is not None:
                    evidence.append({
                        "attempt": attempt_num,
                        "attempt_id": attempt_id,
                        "ref": result_ref,
                        "trace_bytes": trace.size(run_id, attempt_id),
                    })

            # Latest banked finding: what the agent actually returned on an 'ok'
            # result. Retried tickets bank one row per success, so take the
            # newest by id. ``answer`` is the prose form when the playbook's
            # result doc carries one; structured docs keep answer null and are
            # read from ``finding.json``.
            finding = None
            answer = None
            finding_row = conn.execute(
                """SELECT id, kind, json, created_at FROM findings
                   WHERE ticket_id=? ORDER BY id DESC LIMIT 1""",
                (ticket_id,),
            ).fetchone()
            if finding_row is not None:
                try:
                    finding_json = json.loads(finding_row[2])
                except json.JSONDecodeError:
                    finding_json = None
                if finding_json is not None:
                    finding = {
                        "id": finding_row[0],
                        "kind": finding_row[1],
                        "created_at": finding_row[3],
                        "json": finding_json,
                    }
                    if isinstance(finding_json, dict):
                        prose = finding_json.get("answer")
                        if isinstance(prose, str) and prose.strip():
                            answer = prose

            # Get history (event stream for this ticket)
            history_rows = conn.execute(
                """SELECT id, ts, kind, message, data_json
                   FROM events WHERE ticket_id=? ORDER BY id""",
                (ticket_id,),
            ).fetchall()
            history = []
            for row in history_rows:
                history.append({
                    "id": row[0],
                    "ts": row[1],
                    "kind": row[2],
                    "message": row[3],
                    "data": json.loads(row[4]) if row[4] else {},
                })

            # Derive reason (human-readable explanation of current state)
            reason = None
            if state == "needs_human":
                if reduction_id is not None:
                    # Flagged by reduction
                    red_row = conn.execute(
                        """SELECT review_state, json FROM reductions WHERE id=?""",
                        (reduction_id,),
                    ).fetchone()
                    if red_row:
                        review_state, red_json_str = red_row
                        red_json = json.loads(red_json_str)
                        cause = red_json.get("cause_category", "")
                        sig = red_json.get("signature", "")
                        summary = f"{cause}: {sig}" if cause and sig else cause or sig or "reduction"
                        reason = f"Flagged for human review by reduction #{reduction_id} ({review_state}): {summary}"
                else:
                    # Guard-routed (re-verify override / tripped guard): the
                    # needs_human event carries the truthful explanation. The
                    # latest attempt on this path is an 'ok' success whose tokens
                    # ('goal_met') would mislead, so prefer the event message and
                    # fall back to an attempt only when it genuinely failed.
                    event_row = conn.execute(
                        """SELECT message FROM events WHERE ticket_id=? AND kind='needs_human'
                           ORDER BY id DESC LIMIT 1""",
                        (ticket_id,),
                    ).fetchone()
                    if event_row and event_row[0]:
                        msg = event_row[0]
                        reason = (
                            "Independent re-verify did not confirm the reported "
                            "result; routed for human review."
                            if msg == "re-verify override"
                            else msg
                        )
                    if reason is None and attempt_rows:
                        latest_attempt = attempt_rows[-1]
                        if latest_attempt[3] != "ok":  # outcome
                            term_reason = latest_attempt[4]
                            error_summary = latest_attempt[8]
                            if error_summary:
                                reason = f"{term_reason}: {error_summary}"
                            elif term_reason:
                                reason = term_reason
            elif state == "failed":
                # Get from latest attempt
                if attempt_rows:
                    latest_attempt = attempt_rows[-1]
                    term_reason = latest_attempt[4]
                    error_summary = latest_attempt[8]
                    if error_summary:
                        reason = f"{term_reason}: {error_summary}"
                    elif term_reason:
                        reason = term_reason
                if reason is None:
                    # Fallback to latest ticket_failed event data
                    event_row = conn.execute(
                        """SELECT data_json FROM events WHERE ticket_id=? AND kind='ticket_failed'
                           ORDER BY id DESC LIMIT 1""",
                        (ticket_id,),
                    ).fetchone()
                    if event_row and event_row[0]:
                        event_data = json.loads(event_row[0])
                        reason = event_data.get("reason")
                if reason is None:
                    # Operator-abandoned tickets carry no attempt/ticket_failed row.
                    event_row = conn.execute(
                        """SELECT 1 FROM events WHERE ticket_id=? AND kind='ticket_abandoned'
                           LIMIT 1""",
                        (ticket_id,),
                    ).fetchone()
                    if event_row:
                        reason = "Abandoned by operator"
            elif state == "parked":
                reason = f"No capacity for resource '{resource_req}'"

            # Get reduction summary if reduction_id set
            reduction_summary = None
            if reduction_id is not None:
                red_row = conn.execute(
                    """SELECT kind, review_state, json FROM reductions WHERE id=?""",
                    (reduction_id,),
                ).fetchone()
                if red_row:
                    reduction_summary = {
                        "id": reduction_id,
                        "kind": red_row[0],
                        "review_state": red_row[1],
                        "json": json.loads(red_row[2]),
                    }

            # A non-terminal ticket under a terminal run can never be claimed
            # (dispatch only selects tickets whose run is running). Say so —
            # this is the whole explanation for a ticket sitting in 'queued'.
            if reason is None and run_state in TERMINAL_RUN_STATES and state not in ("done", "failed"):
                reason = (
                    f"Run {run_id!r} is {run_state}, so nothing is dispatching this "
                    f"ticket. Reopen the run to pick it up again."
                )

            # Get available actions
            available_actions = _available_actions(state, reduction_id)

            return {
                "ticket": ticket,
                "payload": payload,
                "result": result,
                "attempt_timeline": attempt_timeline,
                "evidence": evidence,
                "finding": finding,
                "answer": answer,
                "history": history,
                "reason": reason,
                "reduction": reduction_summary,
                "available_actions": available_actions,
            }
        finally:
            conn.close()

    @app.get("/api/attempts/{attempt_id}/trace")
    def get_attempt_trace(
        attempt_id: int,
        raw: bool = Query(False),
        _: None = Depends(require_auth_read),
    ) -> dict[str, Any]:
        """The worker's own transcript for one attempt.

        Read from ``HERMES_HOME/runs/<run>/traces/<attempt>.jsonl``, which the
        engine captured at result time (``engine.trace``). Nothing is fetched
        from a host here -- by now the host may be gone and the agent tool may
        have pruned its own state; the point of capturing early is that this
        read is a local one.

        ``raw=1`` returns the file exactly as captured. The default returns it
        flattened into readable records (``server.trace_view``), which is the
        same content classified, not a subset of it.

        404 when the attempt is unknown, or when no trace was captured for it --
        an older run, an agent that cannot name its trace, a host that was
        already gone. The message says which.
        """
        home = config.resolve_home()
        conn = connect(str(home / "queue.db"))
        try:
            row = conn.execute(
                """SELECT a.ticket_id, a.attempt, a.result_ref, t.run_id
                   FROM attempts a JOIN tickets t ON t.id = a.ticket_id
                   WHERE a.id = ?""",
                (attempt_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            raise HTTPException(status_code=404, detail=f"No attempt {attempt_id}")
        ticket_id, attempt_num, result_ref, run_id = row

        content = trace.read(run_id, attempt_id)
        if content is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No trace was captured for attempt {attempt_num} of "
                    f"{ticket_id}. Traces are captured when a result is recorded, "
                    f"so runs from before that, and agents that cannot locate "
                    f"their own transcript, do not have one."
                ),
            )

        head = {
            "attempt_id": attempt_id,
            "attempt": attempt_num,
            "ticket_id": ticket_id,
            "run_id": run_id,
            "ref": result_ref,
        }
        if raw:
            return {**head, "raw": content, "bytes": len(content.encode("utf-8"))}
        return {**head, **trace_view.normalize(content)}

    @app.get("/api/crew")
    def get_crew(_: None = Depends(require_auth_read)) -> list[dict[str, Any]]:
        """Get all crew members with parsed resources, capabilities, and health.

        Returns crew members from the crew table with:
        - id, site, state (idle|busy|down|draining)
        - resources: parsed resources_json
        - capabilities: parsed capabilities
        - current_ticket, current_run, current_phase, current_elapsed_s: the
          ticket dispatched to the host, or null
        - last_heartbeat, heartbeat_age_s
        - health: parsed health_json (may be null if never set)

        Fleet-wide: a host outlives a run. What a host is working on is derived
        from tickets.worker_host; the engine never writes crew.current_ticket or
        a 'busy' state. An idle host with a ticket reads busy; draining and
        down outrank a ticket still finishing.
        """
        import time
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # worker_host stays set once a ticket leaves dispatched, so only
            # in-flight states count. Two masters can each have a ticket on
            # one host; the row shows the latest claim.
            rows = conn.execute(
                """SELECT c.id, c.site, c.state, c.capabilities, c.resources_json,
                          c.health_json, c.last_heartbeat,
                          t.id, t.run_id, t.phase, t.updated_at
                   FROM crew c
                   LEFT JOIN tickets t ON t.id = (
                       SELECT id FROM tickets
                        WHERE worker_host = c.id AND state IN ('dispatched', 'running')
                        ORDER BY updated_at DESC LIMIT 1)
                   ORDER BY c.id"""
            ).fetchall()
            now = time.time()

            crew = []
            for row in rows:
                (
                    host_id, site, state, capabilities_json, resources_json,
                    health_json, last_heartbeat,
                    ticket_id, run_id, phase, claimed_at
                ) = row

                # Parse JSON fields
                capabilities = json.loads(capabilities_json)
                resources = json.loads(resources_json)
                health = json.loads(health_json) if health_json else None

                if ticket_id and state == "idle":
                    state = "busy"

                crew.append({
                    "id": host_id,
                    "site": site,
                    "state": state,
                    "capabilities": capabilities,
                    "resources": resources,
                    "health": health,
                    "current_ticket": ticket_id,
                    "current_run": run_id,
                    "current_phase": phase,
                    "current_elapsed_s": max(0, now - claimed_at) if ticket_id else None,
                    "last_heartbeat": last_heartbeat,
                    "heartbeat_age_s": (
                        max(0, now - last_heartbeat) if last_heartbeat is not None else None
                    ),
                })

            return crew
        finally:
            conn.close()

    @app.get("/api/leases")
    def get_leases(host: str | None = None, _: None = Depends(require_auth_read)) -> list[dict[str, Any]]:
        """Get active (live) leases with optional host filter.

        Returns leases from the leases table where expires_at > now.
        Optional query param:
        - host: filter by host

        Each lease includes:
        - id, run_id, resource_class, ticket_id, host
        - acquired_at, ttl_s, expires_at
        - remaining_s: max(0, expires_at - now)
        """
        import time
        now = time.time()

        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Build query: only live leases (expires_at > now)
            query = """
                SELECT id, run_id, resource_class, ticket_id, host,
                       acquired_at, ttl_s, expires_at
                FROM leases
                WHERE expires_at > ?
            """
            params: list[Any] = [now]

            if host:
                query += " AND host=?"
                params.append(host)

            query += " ORDER BY id"

            rows = conn.execute(query, params).fetchall()

            leases = []
            for row in rows:
                (
                    lease_id, run_id, resource_class, ticket_id, lease_host,
                    acquired_at, ttl_s, expires_at
                ) = row

                # Compute remaining_s
                remaining_s = max(0, expires_at - now)

                leases.append({
                    "id": lease_id,
                    "run_id": run_id,
                    "resource_class": resource_class,
                    "ticket_id": ticket_id,
                    "host": lease_host,
                    "acquired_at": acquired_at,
                    "ttl_s": ttl_s,
                    "expires_at": expires_at,
                    "remaining_s": remaining_s,
                })

            return leases
        finally:
            conn.close()

    @app.get("/api/events")
    def get_events(
        since: int = 0,
        kind: str | None = None,
        limit: int = 200,
        order: Literal["asc", "desc"] = "asc",
        run: str | None = None,
        before: int | None = None,
        _: None = Depends(require_auth_read)
    ) -> list[dict[str, Any]]:
        """Get events from the event feed.

        Query params (all optional):
        - order: 'asc' (default) or 'desc'; anything else is a 422
        - since: order=asc only; return events with id > since (default 0)
        - kind: Filter to specific event kind (default None = all kinds)
        - limit: Max number of events to return (default 200; 1..1000 with order=desc)
        - run: order=desc only; only this run's events (empty = absent)
        - before: order=desc only; only events with id < before

        order=asc returns events ordered by id ascending (events.since); order=desc
        returns the newest first (events.latest). Fields:
        id, ts, kind, run_id, ticket_id, host, message, data (parsed).
        """
        from engine import events

        run = run or None  # an empty run counts as absent
        if order == "asc":
            if run is not None or before is not None:
                raise HTTPException(status_code=400, detail="run and before need order=desc")
        else:
            if since != 0:
                raise HTTPException(status_code=400, detail="since needs order=asc")
            if not 1 <= limit <= 1000:
                raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")

        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            if order == "desc":
                return events.latest(conn, run_id=run, kind=kind, before=before, limit=limit)
            # Reuse events.since with optional kind filter
            return events.since(conn, after_id=since, limit=limit, kind=kind)
        finally:
            conn.close()

    @app.get("/api/events/kinds")
    def get_event_kinds(_: None = Depends(require_auth_read)) -> list[str]:
        """Get distinct event kinds present in the database.

        Returns a sorted list of event kinds (SELECT DISTINCT kind FROM events ORDER BY kind).
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT kind FROM events ORDER BY kind"
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    @app.get("/api/runs/{run_id}/reductions")
    def get_reductions(run_id: str, phase: str | None = None, _: None = Depends(require_auth_read)) -> list[dict[str, Any]]:
        """Get reductions for a run with optional phase filter.

        Returns reductions with parsed json, de-duplicated member_ticket_ids
        (union of json.member_ticket_ids and json.needs_human_ticket_ids),
        and member_tickets with real states from the tickets table.

        Query params:
        - phase: filter to specific phase (optional)

        Returns 404 if run not found.
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Check if run exists
            run_row = conn.execute(
                "SELECT id FROM runs WHERE id=?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

            # Build query with optional phase filter
            query = """
                SELECT id, run_id, phase, kind, json, review_state
                FROM reductions
                WHERE run_id=?
            """
            params: list[Any] = [run_id]

            if phase:
                query += " AND phase=?"
                params.append(phase)

            query += " ORDER BY id"

            rows = conn.execute(query, params).fetchall()

            reductions = []
            for row in rows:
                (rid, r_run_id, r_phase, r_kind, r_json, r_review_state) = row

                # Parse json
                reduction_json = json.loads(r_json)

                # Compute de-duplicated union of member_ticket_ids
                member_ids_from_json = reduction_json.get("member_ticket_ids") or []
                needs_human_ids = reduction_json.get("needs_human_ticket_ids") or []

                # Order-stable de-duplication: preserve first occurrence
                seen = set()
                member_ticket_ids = []
                for mid in member_ids_from_json + needs_human_ids:
                    if mid not in seen:
                        seen.add(mid)
                        member_ticket_ids.append(mid)

                # Fetch member tickets with real states from tickets table
                member_tickets = []
                for mid in member_ticket_ids:
                    ticket_row = conn.execute(
                        """SELECT id, state, phase
                           FROM tickets WHERE id=?""",
                        (mid,),
                    ).fetchone()
                    if ticket_row:
                        member_tickets.append({
                            "id": ticket_row[0],
                            "state": ticket_row[1],
                            "phase": ticket_row[2],
                        })

                reductions.append({
                    "id": rid,
                    "run_id": r_run_id,
                    "phase": r_phase,
                    "kind": r_kind,
                    "json": reduction_json,
                    "review_state": r_review_state,
                    "member_ticket_ids": member_ticket_ids,
                    "member_tickets": member_tickets,
                })

            return reductions
        finally:
            conn.close()

    @app.get("/api/runs/{run_id}/metrics")
    def get_run_metrics(
        run_id: str,
        bucket_s: int = Query(300, ge=1),
        _: None = Depends(require_auth_read)
    ) -> dict[str, Any]:
        """Get time-bucketed metrics for a run.

        Aggregates REAL metrics from events/attempts tables with deterministic time range.

        Args:
            run_id: Run ID
            bucket_s: Bucket width in seconds (default 300 = 5 minutes). Widened
                when the run would need more than METRICS_MAX_BUCKETS; the response's
                bucket_s is the width actually used.

        Returns:
            {
                run_id: str,
                bucket_s: int,
                buckets: [
                    {
                        t_start: float,
                        throughput: int,  # attempts ended in bucket
                        done_cumulative: int,  # cumulative done outcomes
                        failed_cumulative: int,  # cumulative failed outcomes
                        error_rate: float,  # failed/total per bucket
                        busy_hosts: int  # distinct hosts with one of this run's attempts in the bucket
                    }
                ]
            }

        Buckets span from run.created_at to latest event/attempt timestamp (deterministic).
        Done/failed cumulative derived from attempts.outcome (ok vs driver_failed/infra_failed).
        Busy hosts come from this run's own recorded attempts, [started_at, ended_at];
        an attempt still in flight has no row yet, so it shows once it ends.

        Returns 404 if run not found.
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Check if run exists and get created_at
            run_row = conn.execute(
                "SELECT id, created_at FROM runs WHERE id=?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

            run_created_at = run_row[1]

            # Tickets by state: totals count attempts, and a ticket held in
            # needs_human has an ok attempt behind it but is not done.
            by_state = dict(conn.execute(
                "SELECT state, COUNT(*) FROM tickets WHERE run_id=? GROUP BY state",
                (run_id,),
            ).fetchall())

            # Find latest timestamp across events and attempts for this run
            # Events: scope by run_id; the fleet's crew events are not this run's
            # Attempts: scope via tickets join

            # Latest event ts for this run
            event_ts_row = conn.execute(
                "SELECT MAX(ts) FROM events WHERE run_id=?",
                (run_id,)
            ).fetchone()
            max_event_ts = event_ts_row[0] if event_ts_row and event_ts_row[0] else None

            # Latest attempt ts (ended_at) for this run's tickets
            attempt_ts_row = conn.execute(
                """SELECT MAX(a.ended_at)
                   FROM attempts a
                   JOIN tickets t ON a.ticket_id = t.id
                   WHERE t.run_id=?""",
                (run_id,)
            ).fetchone()
            max_attempt_ts = attempt_ts_row[0] if attempt_ts_row and attempt_ts_row[0] else None

            # Determine range end (latest of event/attempt)
            range_end = run_created_at  # Default to run start
            if max_event_ts:
                range_end = max(range_end, max_event_ts)
            if max_attempt_ts:
                range_end = max(range_end, max_attempt_ts)

            # If no events/attempts beyond run start, return empty buckets
            if range_end == run_created_at and max_event_ts is None and max_attempt_ts is None:
                return {
                    "run_id": run_id,
                    "bucket_s": bucket_s,
                    "buckets": [],
                    "totals": {
                        "attempts": 0,
                        "done": 0,
                        "failed": 0,
                        "results": 0,
                        "tickets": 0,
                    },
                    "retry_rate": 0.0,
                    "mean_time_to_result_s": None,
                    "by_phase": [],
                    "by_state": by_state,
                }

            # Generate buckets from run_created_at to range_end
            span = range_end - run_created_at
            bucket_s = max(bucket_s, math.ceil(span / METRICS_MAX_BUCKETS))
            num_buckets = math.ceil(span / bucket_s)
            if num_buckets == 0:
                num_buckets = 1  # At least one bucket if there's any data

            # Fetch all attempts for this run (with all required columns for both buckets and aggregates)
            all_attempts = conn.execute(
                """SELECT a.id, a.phase, a.ticket_id, a.attempt, a.started_at, a.ended_at, a.outcome,
                          a.host
                   FROM attempts a
                   JOIN tickets t ON a.ticket_id = t.id
                   WHERE t.run_id=?
                   ORDER BY a.id""",
                (run_id,)
            ).fetchall()

            def bucket_of(ts: float) -> int:
                # The last attempt defines range_end, so it can land exactly on
                # the final edge; it belongs to the last bucket, not past it.
                return min(max(int((ts - run_created_at) // bucket_s), 0), num_buckets - 1)

            # One pass: each ended attempt counts in the bucket it ended in as
            # [done, failed, ended], and marks its host busy in every bucket its
            # [started_at, ended_at] overlaps.
            # ponytail: O(attempts x buckets spanned), bounded by METRICS_MAX_BUCKETS.
            ended_counts = [[0, 0, 0] for _ in range(num_buckets)]
            busy: list[set[str]] = [set() for _ in range(num_buckets)]
            for row in all_attempts:
                if row[5] is None:
                    continue
                last = bucket_of(row[5])
                ended_counts[last][2] += 1
                if row[6] == 'ok':
                    ended_counts[last][0] += 1
                elif row[6] in ('driver_failed', 'infra_failed'):
                    ended_counts[last][1] += 1
                first = bucket_of(row[4]) if row[4] is not None else last
                for j in range(first, last + 1):
                    busy[j].add(row[7])

            buckets = []
            # Cumulative done/failed are monotonic non-decreasing (accumulated from non-negative per-bucket counts)
            done_cumulative = 0
            failed_cumulative = 0

            for i in range(num_buckets):
                bucket_start = run_created_at + i * bucket_s

                # Throughput: attempts ended in [bucket_start, bucket_end)
                bucket_done, bucket_failed, throughput = ended_counts[i]

                # Error rate for this bucket
                error_rate = (bucket_failed / throughput) if throughput else 0.0

                # Update cumulative done/failed (all attempts up to bucket_end)
                done_cumulative += bucket_done
                failed_cumulative += bucket_failed

                buckets.append({
                    "t_start": bucket_start,
                    "throughput": throughput,
                    "done_cumulative": done_cumulative,
                    "failed_cumulative": failed_cumulative,
                    "error_rate": error_rate,
                    "busy_hosts": len(busy[i]),
                })

            # Compute aggregates from all_attempts
            # totals
            total_attempts = len(all_attempts)
            done_count = sum(1 for row in all_attempts if row[6] == "ok")
            failed_count = sum(1 for row in all_attempts if row[6] in ("driver_failed", "infra_failed"))
            results_count = done_count + failed_count
            distinct_tickets = len(set(row[2] for row in all_attempts))

            totals = {
                "attempts": total_attempts,
                "done": done_count,
                "failed": failed_count,
                "results": results_count,
                "tickets": distinct_tickets,
            }

            # retry_rate: tickets with max attempt > 1 / total tickets
            if distinct_tickets == 0:
                retry_rate = 0.0
            else:
                ticket_max_attempts = {}
                for row in all_attempts:
                    ticket_id = row[2]
                    attempt_num = row[3]
                    if ticket_id not in ticket_max_attempts:
                        ticket_max_attempts[ticket_id] = attempt_num
                    else:
                        ticket_max_attempts[ticket_id] = max(ticket_max_attempts[ticket_id], attempt_num)
                retried_tickets = sum(1 for max_att in ticket_max_attempts.values() if max_att > 1)
                retry_rate = retried_tickets / distinct_tickets

            # mean_time_to_result_s: mean of (ended_at - started_at) over rows with both non-null
            durations = []
            for row in all_attempts:
                started = row[4]
                ended = row[5]
                if started is not None and ended is not None:
                    durations.append(ended - started)

            if len(durations) > 0:
                mean_time_to_result_s = sum(durations) / len(durations)
            else:
                mean_time_to_result_s = None

            # by_phase: per-phase stats, ordered by first appearance
            phase_data = {}
            phase_order = []
            for row in all_attempts:
                phase = row[1]
                if phase not in phase_data:
                    phase_data[phase] = {
                        "tickets": set(),
                        "durations": [],
                        "total": 0,
                        "failed": 0,
                    }
                    phase_order.append(phase)

                ticket_id = row[2]
                started = row[4]
                ended = row[5]
                outcome = row[6]

                phase_data[phase]["tickets"].add(ticket_id)
                phase_data[phase]["total"] += 1
                if outcome in ("driver_failed", "infra_failed"):
                    phase_data[phase]["failed"] += 1
                if started is not None and ended is not None:
                    phase_data[phase]["durations"].append(ended - started)

            by_phase = []
            for phase in phase_order:
                data = phase_data[phase]
                ticket_count = len(data["tickets"])
                if len(data["durations"]) > 0:
                    mean_time_s = sum(data["durations"]) / len(data["durations"])
                else:
                    mean_time_s = None
                failure_pct = (data["failed"] / data["total"] * 100.0) if data["total"] > 0 else 0.0

                by_phase.append({
                    "phase": phase,
                    "tickets": ticket_count,
                    "mean_time_s": mean_time_s,
                    "failure_pct": failure_pct,
                })

            return {
                "run_id": run_id,
                "bucket_s": bucket_s,
                "buckets": buckets,
                "totals": totals,
                "retry_rate": retry_rate,
                "mean_time_to_result_s": mean_time_to_result_s,
                "by_phase": by_phase,
                "by_state": by_state,
            }
        finally:
            conn.close()

    # --- Crew Control Endpoints (D2a) ---

    def _serialize_health_checklist(host: str, report) -> dict[str, Any]:
        """Serialize a HealthReport into the checklist response shape.

        Shared helper for probe + reprobe endpoints.
        """
        return {
            "host": host,
            "ok": report.ok,
            "reachable": report.reachable,
            "agent_ok": report.agent_ok,
            "auth_ok": report.auth_ok,
            "workspace_ready": report.workspace_ready,
            "guard_installed": report.guard_installed,
            "resources": report.resources,
            "latency_ms": report.latency_ms,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail}
                for c in report.checks
            ],
        }

    @app.post("/api/crew/probe")
    def probe_crew_host(
        request_body: dict[str, Any],
        _: None = Depends(require_auth)
    ) -> dict[str, Any]:
        """Probe a host's health (read-only health check).

        Body: {host, site, agent?}
        Returns: {host, ok, reachable, agent_ok, auth_ok, workspace_ready,
                 guard_installed, resources, latency_ms, checks}

        400/404 if site/agent unknown.
        """
        from engine import site as site_module, agent as agent_module

        host = request_body.get("host")
        site_name = request_body.get("site")
        agent_name = request_body.get("agent", "claude")

        if not host or not site_name:
            raise HTTPException(status_code=400, detail="Missing required fields: host, site")

        # Load site and agent
        try:
            site_obj = site_module.load(site_name)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

        try:
            agent_obj = agent_module.load(agent_name)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

        # Run health check (read-only, no provisioning beyond what health needs)
        report = site_obj.health(host, agent_obj)

        return _serialize_health_checklist(host, report)

    @app.post("/api/crew")
    def add_crew_member(
        request_body: dict[str, Any],
        _: None = Depends(require_auth)
    ) -> dict[str, Any]:
        """Admit a crew member (provision + health-gate).

        Body: {host, site, agent?, base_ref?}
        Returns: {id, site, state, resources, health, ...} on success
        422 with failing-checks detail if unhealthy (no row inserted)
        400/404 if site/agent unknown.
        """
        from engine import site as site_module, agent as agent_module, crew

        host = request_body.get("host")
        site_name = request_body.get("site")
        agent_name = request_body.get("agent", "claude")
        base_ref = request_body.get("base_ref", "main")

        if not host or not site_name:
            raise HTTPException(status_code=400, detail="Missing required fields: host, site")

        # Load site and agent
        try:
            site_obj = site_module.load(site_name)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

        try:
            agent_obj = agent_module.load(agent_name)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

        # Admit the crew member
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            crew.add(conn, site_obj, agent_obj, host, base_ref)
        except ValueError as e:
            # Unhealthy host - return 422 with failing checks detail
            raise HTTPException(status_code=422, detail=str(e))
        finally:
            conn.close()

        # Return the admitted crew member exactly as the crew list shows it
        for member in get_crew(None):
            if member["id"] == host:
                return member
        raise HTTPException(status_code=500, detail="Crew member admitted but not found")

    @app.post("/api/crew/{host}/reprobe")
    def reprobe_crew_member(
        host: str,
        request_body: dict[str, Any] = None,
        _: None = Depends(require_auth)
    ) -> dict[str, Any]:
        """Re-probe a crew member's health and update health_json.

        Body: {agent?}
        Returns: same checklist shape as /probe
        404 if host not in crew.
        """
        from engine import site as site_module, agent as agent_module
        import time

        # Get the crew member to determine its site
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT site FROM crew WHERE id=?",
                (host,)
            ).fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail=f"Crew member {host!r} not found")

            site_name = row[0]
        finally:
            conn.close()

        # Determine agent (from body or default)
        agent_name = "claude"
        if request_body:
            agent_name = request_body.get("agent", "claude")

        # Load site and agent
        try:
            site_obj = site_module.load(site_name)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

        try:
            agent_obj = agent_module.load(agent_name)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

        # Run health check
        report = site_obj.health(host, agent_obj)

        # Update crew row's health_json and last_heartbeat
        conn = connect(db_path)
        try:
            health_json = json.dumps({
                "reachable": report.reachable,
                "agent_ok": report.agent_ok,
                "auth_ok": report.auth_ok,
                "workspace_ready": report.workspace_ready,
                "guard_installed": report.guard_installed,
                "latency_ms": report.latency_ms,
            })

            now = time.time()
            conn.execute(
                """UPDATE crew SET health_json=?, last_heartbeat=?
                   WHERE id=?""",
                (health_json, now, host)
            )
            conn.commit()
        finally:
            conn.close()

        return _serialize_health_checklist(host, report)

    @app.post("/api/crew/{host}/drain")
    def drain_crew_member(
        host: str,
        _: None = Depends(require_auth)
    ) -> dict[str, Any]:
        """Drain a crew member (set state to draining).

        Returns: {state: "draining"}
        404 if host not in crew.
        """
        from engine import crew

        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Check if host exists
            row = conn.execute(
                "SELECT id FROM crew WHERE id=?",
                (host,)
            ).fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail=f"Crew member {host!r} not found")

            # Drain the host
            crew.drain(conn, host)

            return {"state": "draining"}
        finally:
            conn.close()

    @app.delete("/api/crew/{host}")
    def remove_crew_member(
        host: str,
        _: None = Depends(require_auth)
    ) -> dict[str, Any]:
        """Remove a crew member.

        Returns: {status: "removed"}
        404 if host not in crew.
        """
        from engine import crew

        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Check if host exists
            row = conn.execute(
                "SELECT id FROM crew WHERE id=?",
                (host,)
            ).fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail=f"Crew member {host!r} not found")

            # Remove the host
            crew.remove(conn, host)

            return {"status": "removed"}
        finally:
            conn.close()

    # --- Run Control Endpoints (D1a) ---

    def _guarded_transition(
        table: str,
        id_value: str | int,
        exists_sql: str,
        mutate_fn: Any,
        result_field: str,
        result_sql: str,
        action: Optional[str] = None,
    ) -> dict[str, Any]:
        """Helper for transition endpoints: existence check → 404, ValueError → 409, return new state.

        When ``action`` is given (ticket operator actions), the ticket's current
        state decides legality via the same ``_available_actions`` map the detail
        endpoint advertises — so the API and the UI action menu never disagree. The
        engine primitive's own guard remains as a backstop.
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Explicit existence check: 404 if not found
            exists = conn.execute(exists_sql, (id_value,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail=f"{table.capitalize()} {id_value!r} not found")

            # Ticket actions: gate on the advertised available_actions (single
            # source of truth), so an action the menu hides can never succeed.
            if action is not None:
                srow = conn.execute(
                    "SELECT state, reduction_id FROM tickets WHERE id=?", (id_value,)
                ).fetchone()
                state, reduction_id = srow
                allowed = _available_actions(state, reduction_id)
                if action not in allowed:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"action {action!r} is not available for ticket "
                            f"{id_value!r} in state {state!r}; available: {allowed}"
                        ),
                    )

            # Attempt mutation: 409 if ValueError
            try:
                mutate_fn(conn, id_value)
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))

            # Return the new state field
            new_value = conn.execute(result_sql, (id_value,)).fetchone()[0]
            return {result_field: new_value}
        finally:
            conn.close()

    @app.post("/api/runs/{run_id}/pause")
    def pause_run(run_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Pause a running run.

        Returns the run's new state on success.
        404 if run unknown, 409 if illegal transition.
        """
        return _guarded_transition(
            table="run",
            id_value=run_id,
            exists_sql="SELECT 1 FROM runs WHERE id=?",
            mutate_fn=lambda conn, rid: apply_run_action(conn, rid, "pause"),
            result_field="state",
            result_sql="SELECT state FROM runs WHERE id=?",
        )

    @app.post("/api/runs/{run_id}/resume")
    def resume_run(run_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Resume a paused run.

        Returns the run's new state on success.
        404 if run unknown, 409 if illegal transition.
        """
        return _guarded_transition(
            table="run",
            id_value=run_id,
            exists_sql="SELECT 1 FROM runs WHERE id=?",
            mutate_fn=lambda conn, rid: apply_run_action(conn, rid, "resume"),
            result_field="state",
            result_sql="SELECT state FROM runs WHERE id=?",
        )

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Stop a running or paused run.

        Returns the run's new state on success.
        404 if run unknown, 409 if illegal transition.
        """
        return _guarded_transition(
            table="run",
            id_value=run_id,
            exists_sql="SELECT 1 FROM runs WHERE id=?",
            mutate_fn=lambda conn, rid: apply_run_action(conn, rid, "stop"),
            result_field="state",
            result_sql="SELECT state FROM runs WHERE id=?",
        )

    @app.post("/api/runs/{run_id}/reopen")
    def reopen_run(run_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Reopen a finished run (done/stopped/failed) so its tickets dispatch again.

        Returns the run's new state on success.
        404 if run unknown, 409 if the run is not finished.
        """
        return _guarded_transition(
            table="run",
            id_value=run_id,
            exists_sql="SELECT 1 FROM runs WHERE id=?",
            mutate_fn=lambda conn, rid: apply_run_action(conn, rid, "reopen"),
            result_field="state",
            result_sql="SELECT state FROM runs WHERE id=?",
        )

    # --- Ticket Control Endpoints (D3) ---

    @app.post("/api/tickets/{ticket_id:path}/requeue")
    def requeue_ticket(ticket_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Requeue a guard-routed needs_human ticket.

        Returns the ticket's new state on success.
        404 if ticket unknown, 409 if not needs_human.
        """
        from engine.queue import requeue_needs_human

        return _guarded_transition(
            table="ticket",
            id_value=ticket_id,
            exists_sql="SELECT 1 FROM tickets WHERE id=?",
            mutate_fn=requeue_needs_human,
            result_field="state",
            result_sql="SELECT state FROM tickets WHERE id=?",
            action="requeue",
        )

    @app.post("/api/tickets/{ticket_id:path}/abandon")
    def abandon_ticket_endpoint(ticket_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Abandon a non-terminal ticket (operator action).

        Returns the ticket's new state on success.
        404 if ticket unknown, 409 if terminal.
        """
        from engine.queue import abandon_ticket

        return _guarded_transition(
            table="ticket",
            id_value=ticket_id,
            exists_sql="SELECT 1 FROM tickets WHERE id=?",
            mutate_fn=abandon_ticket,
            result_field="state",
            result_sql="SELECT state FROM tickets WHERE id=?",
            action="abandon",
        )

    @app.post("/api/tickets/{ticket_id:path}/retry")
    def retry_ticket_endpoint(ticket_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Retry a failed ticket (operator action).

        Returns the ticket's new state on success.
        404 if ticket unknown, 409 if not failed.
        """
        from engine.queue import retry_ticket

        return _guarded_transition(
            table="ticket",
            id_value=ticket_id,
            exists_sql="SELECT 1 FROM tickets WHERE id=?",
            mutate_fn=retry_ticket,
            result_field="state",
            result_sql="SELECT state FROM tickets WHERE id=?",
            action="retry",
        )

    @app.post("/api/tickets/{ticket_id:path}/priority")
    def set_ticket_priority_endpoint(
        ticket_id: str,
        body: dict[str, Any],
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Set a non-terminal ticket's priority (operator action).

        Body: {"priority": float}

        Returns the ticket's new state on success.
        404 if ticket unknown, 409 if terminal.
        """
        from engine.queue import set_ticket_priority

        priority = body.get("priority")
        if priority is None or not isinstance(priority, (int, float)):
            raise HTTPException(status_code=400, detail="priority must be a number")

        return _guarded_transition(
            table="ticket",
            id_value=ticket_id,
            exists_sql="SELECT 1 FROM tickets WHERE id=?",
            mutate_fn=lambda conn, tid: set_ticket_priority(conn, tid, float(priority)),
            result_field="state",
            result_sql="SELECT state FROM tickets WHERE id=?",
            action="reprioritize",
        )

    # --- Reduction Control Endpoints (D4) ---

    @app.post("/api/reductions/{reduction_id:int}/accept")
    def accept_reduction_endpoint(reduction_id: int, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Accept a pending reduction.

        Returns the reduction's new review_state on success.
        404 if reduction unknown, 409 if not pending.
        """
        from engine.queue import accept_reduction

        return _guarded_transition(
            table="reduction",
            id_value=reduction_id,
            exists_sql="SELECT 1 FROM reductions WHERE id=?",
            mutate_fn=accept_reduction,
            result_field="review_state",
            result_sql="SELECT review_state FROM reductions WHERE id=?",
        )

    @app.post("/api/reductions/{reduction_id:int}/reject")
    def reject_reduction_endpoint(reduction_id: int, _: None = Depends(require_auth)) -> dict[str, Any]:
        """Reject a pending reduction.

        Returns the reduction's new review_state on success.
        404 if reduction unknown, 409 if not pending.
        """
        from engine.queue import reject_reduction

        return _guarded_transition(
            table="reduction",
            id_value=reduction_id,
            exists_sql="SELECT 1 FROM reductions WHERE id=?",
            mutate_fn=reject_reduction,
            result_field="review_state",
            result_sql="SELECT review_state FROM reductions WHERE id=?",
        )

    @app.websocket("/api/ws")
    async def websocket_endpoint(websocket: WebSocket, since: int = None, token: str = Query(None)):
        """WebSocket endpoint for live event stream (auth required).

        Polls the real events table and pushes new events to connected clients.

        Query params:
        - since: Start cursor (event id). Default: current max event id (only new events).
                 Use since=0 to replay from start.
        - token: Bearer token (required)

        Messages:
        - hello: {type: "hello", last_id: <cursor>} on connect
        - event: {type: "event", event: {...}} for each new event

        Auth: Closes with code 4401 if token missing/invalid.
        """
        # Accept connection first so we can close with a code
        await websocket.accept()

        # Validate token (from query param or potentially from Authorization header)
        # Note: WebSocket in FastAPI doesn't easily support HTTPBearer, so we rely on ?token=
        provided_token = token

        # Try to get token from headers if not in query
        if not provided_token:
            auth_header = websocket.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                provided_token = auth_header[7:]

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(provided_token or "", app_token or ""):
            # Close with custom code 4401
            await websocket.close(code=4401)
            return

        # Get poll interval from config
        poll_interval = config.ws_poll_s()

        # Determine starting cursor: if since is provided use it, else current max event id
        home = config.resolve_home()
        db_path = str(home / "queue.db")

        if since is None:
            # Default: get current max event id (only new events)
            conn = connect(db_path)
            try:
                max_id_row = conn.execute("SELECT MAX(id) FROM events").fetchone()
                last_id = max_id_row[0] if max_id_row[0] is not None else 0
            finally:
                conn.close()
        else:
            last_id = since

        # Send hello message with initial cursor
        await websocket.send_json({"type": "hello", "last_id": last_id})

        # Poll loop
        try:
            while True:
                # Poll for new events (fresh connection per poll)
                conn = connect(db_path)
                try:
                    from engine import events
                    new_events = events.since(conn, after_id=last_id, limit=200)
                finally:
                    conn.close()

                # Send each new event
                for event in new_events:
                    await websocket.send_json({"type": "event", "event": event})
                    last_id = event["id"]

                # Wait before next poll
                await asyncio.sleep(poll_interval)

        except WebSocketDisconnect:
            # Clean disconnect - just break the loop
            pass
        except Exception as e:
            # Log unexpected errors but don't crash the server
            logger = log.get_logger("server.websocket")
            logger.exception("WebSocket error")
        finally:
            # Ensure connection is closed
            try:
                await websocket.close()
            except Exception:
                pass

    # --- SPA Serving + Token Injection (D1a) ---

    # Determine dist dir from config
    dist_dir = Path(config.web_dist())

    @app.get("/", response_class=HTMLResponse)
    def serve_spa(_: None = Depends(require_auth_read)) -> str:
        """Serve the SPA index.html with token bootstrap injection (loopback only).

        On loopback: injects window.__HERMES_TOKEN__ and window.__HERMES_BIND__="loopback"
        On non-loopback: only injects window.__HERMES_BIND__="remote" (no token)
        """
        index_path = dist_dir / "index.html"

        if not index_path.exists():
            # Return a placeholder if dist dir/index.html is absent
            return """<!DOCTYPE html>
<html>
<head><title>Hermes</title></head>
<body>
<p>Hermes control plane (SPA not built)</p>
</body>
</html>"""

        # Read index.html
        html = index_path.read_text()

        # Inject token bootstrap (loopback only) and bind marker
        if loopback:
            # Inject token + loopback marker before </head>
            injection = f'<script>window.__HERMES_TOKEN__="{app_token}";window.__HERMES_BIND__="loopback";</script>'
        else:
            # Only inject remote marker (no token)
            injection = '<script>window.__HERMES_BIND__="remote";</script>'

        # Insert before </head>
        if "</head>" in html:
            html = html.replace("</head>", f"{injection}</head>", 1)
        else:
            # Fallback: prepend to body
            html = injection + html

        return html

    # Serve dist-root static files the SPA references (favicon, icon sprite).
    # Ungated (like /assets) so the browser can fetch the tab icon without a token.
    @app.get("/favicon.svg")
    def serve_favicon() -> FileResponse:
        fpath = dist_dir / "favicon.svg"
        if not fpath.exists():
            raise HTTPException(status_code=404, detail="favicon.svg not found")
        return FileResponse(str(fpath), media_type="image/svg+xml")

    @app.get("/icons.svg")
    def serve_icons() -> FileResponse:
        fpath = dist_dir / "icons.svg"
        if not fpath.exists():
            raise HTTPException(status_code=404, detail="icons.svg not found")
        return FileResponse(str(fpath), media_type="image/svg+xml")

    # Mount static assets if assets dir exists
    assets_dir = dist_dir / "assets"
    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # --- playbook-owned views (spec §4) ---------------------------------

    @app.get("/api/playbooks/{name}/view.js")
    def get_playbook_view_asset(
        name: str, _: None = Depends(require_auth_read)
    ) -> FileResponse:
        """Serve a playbook's built view bundle."""
        obj = view_playbook(name)
        if obj is None:
            raise HTTPException(status_code=404, detail=f"Playbook {name!r} has no view")
        return FileResponse(
            str(obj.view_asset()),
            media_type="text/javascript",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/runs/{run_id}/view")
    def get_run_view(run_id: str, _: None = Depends(require_auth_read)) -> dict[str, Any]:
        """Everything the run's playbook view renders.

        ``view_data`` runs HERE, in the server process: it can read neither the
        playbook's instance state nor the master's environment. A playbook that
        falls back to an env var for something no reduction carries gets THIS
        process's value, so a server started without the env the master ran with
        shows that field's default. Known, and not papered over here -- the fix
        is to put the value on a reduction, in the playbook.
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            try:
                run = load_run(conn, run_id)
            except ValueError:
                raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
            obj = view_playbook(run.playbook)
            if obj is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id!r} has no view")
            rows = conn.execute(
                """SELECT id, run_id, phase, kind, json, review_state
                   FROM reductions WHERE run_id=? ORDER BY id""",
                (run_id,),
            ).fetchall()
            reductions = [
                Reduction(kind=r[3], json=json.loads(r[4]), id=r[0], run_id=r[1],
                          phase=r[2], review_state=r[5])
                for r in rows
            ]
            return obj.view_data(run, reductions)
        finally:
            conn.close()

    @app.get("/api/runs/{run_id}/view/artifact", response_model=None)
    def get_run_view_artifact(
        run_id: str, path: str = "", sha256: str = "", _: None = Depends(require_auth_read)
    ) -> dict[str, Any] | Response:
        """One file from the run's own directory, as text, on demand.

        ``path`` is ``<dir>/<name>`` under ``runs/<run_id>/`` in THIS process's
        HERMES_HOME; ``view_data`` names every file a view may ask for. No
        reduction is read and no recorded path is opened -- those are the
        master's host paths, and a server in a container that mounts only the
        home cannot open them. ``path`` defaults to "" so a missing one reaches
        the handler and gets its 400 after the gate, not FastAPI's 422 before.
        ``images/<name>`` is served as raw bytes under a sandboxing CSP, an
        ``<img>`` being its only reader; an optional ``sha256`` pins its bytes.
        """
        home = config.resolve_home()
        conn = connect(str(home / "queue.db"))
        try:
            row = conn.execute(
                "SELECT playbook FROM runs WHERE id=?", (run_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        # The gate goes ABOVE every 400: with the kill switch on, all three
        # routes 404 (criterion 3), and a 400 here would tell a caller the
        # route is live on a server that has turned it off.
        if view_playbook(row[0]) is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} has no view")
        # Below the run and view gates (their 404s outrank every 400), above
        # the walk: an image path must name one of the two served types.
        image = path.startswith("images/")
        if image and Path(path).suffix not in _IMAGE_TYPES:
            raise HTTPException(
                status_code=400, detail=f"an image must be .svg or .png, not {path!r}"
            )
        fd = _open_run_file(home, run_id, path)
        if image:
            return _image_response(fd, path, sha256)
        try:
            with open(fd, encoding="utf-8", errors="replace") as handle:
                text = handle.read(ARTIFACT_MAX_CHARS + 1)
        except (OSError, ValueError):
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} has no readable {path}")
        return {
            "text": text[:ARTIFACT_MAX_CHARS],
            "truncated": len(text) > ARTIFACT_MAX_CHARS,
        }

    return app
