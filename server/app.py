"""FastAPI control plane server with bearer-token auth, WebSocket live events, and SPA serving with token injection on loopback."""
import asyncio
import json
import math
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Annotated

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles

from engine import config
from engine.db.migrate import connect
from engine.queue import load_run, phase_ticket_counts, set_run_state
from engine import log
from server.auth import load_or_create_token


# Security scheme for bearer token
security = HTTPBearer(auto_error=False)


def is_loopback(bind: str | None) -> bool:
    """Check if bind address is loopback."""
    if bind is None:
        return True
    return bind in ("127.0.0.1", "localhost", "::1")


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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager for startup/shutdown logging."""
        logger.info("API server started")
        yield
        logger.info("API server stopped")

    app = FastAPI(title="Hermes Control Plane", version="0.1.0", lifespan=lifespan)

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

            # Load playbook to get canonical phase order
            from engine import playbook as playbook_module
            # Register example playbook
            import testkit.example_playbook  # noqa: F401
            playbook_obj = playbook_module.load(playbook_name)

            # Build phases array in playbook order
            phases = []
            for phase_name in playbook_obj.phases:
                phase_counts = phase_ticket_counts(conn, run_id, phase_name)
                phases.append({
                    "name": phase_name,
                    "counts": phase_counts,
                    "current": phase_name == current_phase,
                })

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
                SELECT id, run_id, state, phase, resource_req, worker_host,
                       attempts, priority, payload_json, updated_at
                FROM tickets
                WHERE run_id=?
            """
            params: list[Any] = [run_id]

            if state:
                query += " AND state=?"
                params.append(state)
            if phase:
                query += " AND phase=?"
                params.append(phase)
            if resource:
                query += " AND resource_req=?"
                params.append(resource)
            if host:
                query += " AND worker_host=?"
                params.append(host)
            if search:
                query += " AND (id LIKE ? OR payload_json LIKE ?)"
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])

            query += " ORDER BY priority DESC, id"

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

                # Extract subject from payload
                payload = json.loads(payload_json)
                subject = payload.get("goal") or payload.get("subject") or "—"

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

    @app.get("/api/tickets/{ticket_id:path}")
    def get_ticket_detail(ticket_id: str, _: None = Depends(require_auth_read)) -> dict[str, Any]:
        """Get full ticket detail.

        Returns:
        - ticket: all ticket fields including parsed subject and reduction_id
        - payload: parsed payload_json (GoalEnvelope)
        - result: strict latest result (max id attempt) or null
        - attempt_timeline: all attempts ordered oldest→newest
        - evidence: non-null result_refs as {attempt, ref}
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Get ticket
            ticket_row = conn.execute(
                """SELECT id, run_id, phase, state, resource_req, priority,
                          attempts, worker_host, reduction_id, payload_json, created_at, updated_at
                   FROM tickets WHERE id=?""",
                (ticket_id,),
            ).fetchone()

            if ticket_row is None:
                raise HTTPException(status_code=404, detail=f"Ticket {ticket_id!r} not found")

            (
                tid, run_id, phase, state, resource_req, priority,
                attempts, worker_host, reduction_id, payload_json, created_at, updated_at
            ) = ticket_row

            # Parse payload
            payload = json.loads(payload_json)
            subject = payload.get("goal") or payload.get("subject") or "—"

            # Build ticket object
            ticket = {
                "id": tid,
                "run_id": run_id,
                "phase": phase,
                "state": state,
                "resource_req": resource_req,
                "priority": priority,
                "attempts": attempts,
                "host": worker_host,
                "reduction_id": reduction_id,
                "subject": subject,
                "created_at": created_at,
                "updated_at": updated_at,
            }

            # Get all attempts (ordered by id for timeline)
            attempt_rows = conn.execute(
                """SELECT id, attempt, host, outcome, termination_reason,
                          started_at, ended_at, result_ref, error_summary
                   FROM attempts WHERE ticket_id=? ORDER BY id""",
                (ticket_id,),
            ).fetchall()

            # Build attempt_timeline
            attempt_timeline = []
            for row in attempt_rows:
                (
                    attempt_id, attempt_num, host, outcome, term_reason,
                    started_at, ended_at, result_ref, error_summary
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
                })

            # Derive strict latest result (max id attempt)
            result = None
            if attempt_rows:
                latest = attempt_rows[-1]  # Last in id-ordered list
                (
                    _, _, _, outcome, term_reason,
                    started_at, ended_at, result_ref, error_summary
                ) = latest
                result = {
                    "outcome": outcome,
                    "termination_reason": term_reason,
                    "result_ref": result_ref,
                    "error_summary": error_summary,
                    "started_at": started_at,
                    "ended_at": ended_at,
                }

            # Build evidence (non-null result_refs)
            evidence = []
            for i, row in enumerate(attempt_rows):
                result_ref = row[7]  # result_ref column
                attempt_num = row[1]  # attempt column
                if result_ref is not None:
                    evidence.append({
                        "attempt": attempt_num,
                        "ref": result_ref,
                    })

            return {
                "ticket": ticket,
                "payload": payload,
                "result": result,
                "attempt_timeline": attempt_timeline,
                "evidence": evidence,
            }
        finally:
            conn.close()

    @app.get("/api/crew")
    def get_crew(_: None = Depends(require_auth_read)) -> list[dict[str, Any]]:
        """Get all crew members with parsed resources, capabilities, and health.

        Returns crew members from the crew table with:
        - id, site, state (idle|busy|down|draining)
        - resources: parsed resources_json
        - capabilities: parsed capabilities
        - current_ticket, last_heartbeat
        - health: parsed health_json (may be null if never set)
        """
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            rows = conn.execute(
                """SELECT id, site, state, capabilities, resources_json, health_json,
                          current_ticket, last_heartbeat
                   FROM crew
                   ORDER BY id"""
            ).fetchall()

            crew = []
            for row in rows:
                (
                    host_id, site, state, capabilities_json, resources_json,
                    health_json, current_ticket, last_heartbeat
                ) = row

                # Parse JSON fields
                capabilities = json.loads(capabilities_json)
                resources = json.loads(resources_json)
                health = json.loads(health_json) if health_json else None

                crew.append({
                    "id": host_id,
                    "site": site,
                    "state": state,
                    "capabilities": capabilities,
                    "resources": resources,
                    "health": health,
                    "current_ticket": current_ticket,
                    "last_heartbeat": last_heartbeat,
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
        _: None = Depends(require_auth_read)
    ) -> list[dict[str, Any]]:
        """Get events from the event feed.

        Query params (all optional):
        - since: Return events with id > since (default 0)
        - kind: Filter to specific event kind (default None = all kinds)
        - limit: Max number of events to return (default 200)

        Returns events ordered by id ascending with fields:
        id, ts, kind, run_id, ticket_id, host, message, data (parsed).
        """
        from engine import events

        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
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
        bucket_s: int = 300,
        _: None = Depends(require_auth_read)
    ) -> dict[str, Any]:
        """Get time-bucketed metrics for a run.

        Aggregates REAL metrics from events/attempts tables with deterministic time range.

        Args:
            run_id: Run ID
            bucket_s: Bucket width in seconds (default 300 = 5 minutes)

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
                        crew_online: int  # hosts online as of bucket end
                    }
                ]
            }

        Buckets span from run.created_at to latest event/attempt timestamp (deterministic).
        Done/failed cumulative derived from attempts.outcome (ok vs driver_failed/infra_failed).
        Crew online tracks crew_added/crew_health (online) vs crew_down/crew_drained (offline).

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

            # Find latest timestamp across events and attempts for this run
            # Events: scope by run_id (crew events may have null run_id - include all for global crew tracking)
            # Attempts: scope via tickets join

            # Latest event ts (all events, including crew events)
            event_ts_row = conn.execute(
                "SELECT MAX(ts) FROM events WHERE run_id=? OR kind IN ('crew_added', 'crew_health', 'crew_down', 'crew_drained')",
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
                    "buckets": []
                }

            # Generate buckets from run_created_at to range_end
            num_buckets = math.ceil((range_end - run_created_at) / bucket_s)
            if num_buckets == 0:
                num_buckets = 1  # At least one bucket if there's any data

            # Fetch all attempts for this run (with ended_at and outcome)
            attempts = conn.execute(
                """SELECT a.ended_at, a.outcome
                   FROM attempts a
                   JOIN tickets t ON a.ticket_id = t.id
                   WHERE t.run_id=? AND a.ended_at IS NOT NULL
                   ORDER BY a.ended_at""",
                (run_id,)
            ).fetchall()

            # Fetch all crew events (global, not run-scoped - crew is fleet-wide)
            # But for deterministic test behavior, scope to this run's events or use all
            # CHOICE: Include all crew events (global crew tracking)
            crew_events = conn.execute(
                """SELECT ts, kind, host
                   FROM events
                   WHERE kind IN ('crew_added', 'crew_health', 'crew_down', 'crew_drained')
                   ORDER BY ts"""
            ).fetchall()

            buckets = []
            # Cumulative done/failed are monotonic non-decreasing (accumulated from non-negative per-bucket counts)
            done_cumulative = 0
            failed_cumulative = 0

            # Track crew state: dict of host -> online/offline
            crew_state: dict[str, bool] = {}
            crew_event_idx = 0  # Advancing cursor across buckets (single-pass O(events))

            for i in range(num_buckets):
                bucket_start = run_created_at + i * bucket_s
                bucket_end = bucket_start + bucket_s

                # Throughput: attempts ended in [bucket_start, bucket_end)
                bucket_ended = [a for a in attempts if bucket_start <= a[0] < bucket_end]
                throughput = len(bucket_ended)

                # Per-bucket failed/done counts (for error_rate)
                bucket_done = sum(1 for a in bucket_ended if a[1] == 'ok')
                bucket_failed = sum(1 for a in bucket_ended if a[1] in ('driver_failed', 'infra_failed'))

                # Error rate for this bucket
                error_rate = (bucket_failed / len(bucket_ended)) if bucket_ended else 0.0

                # Update cumulative done/failed (all attempts up to bucket_end)
                done_cumulative += bucket_done
                failed_cumulative += bucket_failed

                # Update crew state up to bucket_end (single-cursor advancing from last position)
                while crew_event_idx < len(crew_events):
                    event_ts, event_kind, event_host = crew_events[crew_event_idx]
                    if event_ts >= bucket_end:
                        break
                    if event_kind in ('crew_added', 'crew_health'):
                        crew_state[event_host] = True
                    elif event_kind in ('crew_down', 'crew_drained'):
                        crew_state[event_host] = False
                    crew_event_idx += 1

                # Crew online count at bucket end
                crew_online = sum(1 for online in crew_state.values() if online)

                buckets.append({
                    "t_start": bucket_start,
                    "throughput": throughput,
                    "done_cumulative": done_cumulative,
                    "failed_cumulative": failed_cumulative,
                    "error_rate": error_rate,
                    "crew_online": crew_online,
                })

            return {
                "run_id": run_id,
                "bucket_s": bucket_s,
                "buckets": buckets,
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

        # Fetch and return the admitted crew member
        conn = connect(db_path)
        try:
            row = conn.execute(
                """SELECT id, site, state, capabilities, resources_json, health_json,
                          current_ticket, last_heartbeat
                   FROM crew WHERE id=?""",
                (host,)
            ).fetchone()

            if row is None:
                raise HTTPException(status_code=500, detail="Crew member admitted but not found")

            capabilities = json.loads(row[3])
            resources = json.loads(row[4])
            health = json.loads(row[5]) if row[5] else None

            return {
                "id": row[0],
                "site": row[1],
                "state": row[2],
                "capabilities": capabilities,
                "resources": resources,
                "health": health,
                "current_ticket": row[6],
                "last_heartbeat": row[7],
            }
        finally:
            conn.close()

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
    ) -> dict[str, Any]:
        """Helper for transition endpoints: existence check → 404, ValueError → 409, return new state."""
        home = config.resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Explicit existence check: 404 if not found
            exists = conn.execute(exists_sql, (id_value,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail=f"{table.capitalize()} {id_value!r} not found")

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
            mutate_fn=lambda conn, rid: set_run_state(conn, rid, "paused"),
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
            mutate_fn=lambda conn, rid: set_run_state(conn, rid, "running"),
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
            mutate_fn=lambda conn, rid: set_run_state(conn, rid, "stopped"),
            result_field="state",
            result_sql="SELECT state FROM runs WHERE id=?",
        )

    # --- Ticket Control Endpoints (D3) ---

    @app.post("/api/tickets/{ticket_id}/requeue")
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

    # Mount static assets if assets dir exists
    assets_dir = dist_dir / "assets"
    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    return app
