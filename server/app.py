"""
server.app — FastAPI application.

Minimal control-plane server (Phase A1). Read endpoints over the real queue.db.
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from engine.config import resolve_home
from engine.db.migrate import connect
from engine.queue import load_run, phase_ticket_counts


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="Hermes Control Plane", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        """Health check endpoint.

        Returns status, version, and resolved HERMES_HOME.
        """
        home = resolve_home()
        return {
            "status": "ok",
            "version": "0.1.0",
            "home": str(home),
        }

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        """List all runs with ticket counts by state.

        Returns a list of runs, each with per-state ticket counts.
        """
        home = resolve_home()
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
    def get_run(run_id: str) -> dict[str, Any]:
        """Get a single run by ID with phase ticket counts.

        Returns run details including per-state ticket counts and
        per-phase ticket counts (as an array in playbook phase order).
        """
        home = resolve_home()
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
        home = resolve_home()
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
    def get_ticket_detail(ticket_id: str) -> dict[str, Any]:
        """Get full ticket detail.

        Returns:
        - ticket: all ticket fields including parsed subject
        - payload: parsed payload_json (GoalEnvelope)
        - result: strict latest result (max id attempt) or null
        - attempt_timeline: all attempts ordered oldest→newest
        - evidence: non-null result_refs as {attempt, ref}
        """
        home = resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Get ticket
            ticket_row = conn.execute(
                """SELECT id, run_id, phase, state, resource_req, priority,
                          attempts, worker_host, payload_json, created_at, updated_at
                   FROM tickets WHERE id=?""",
                (ticket_id,),
            ).fetchone()

            if ticket_row is None:
                raise HTTPException(status_code=404, detail=f"Ticket {ticket_id!r} not found")

            (
                tid, run_id, phase, state, resource_req, priority,
                attempts, worker_host, payload_json, created_at, updated_at
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
    def get_crew() -> list[dict[str, Any]]:
        """Get all crew members with parsed resources, capabilities, and health.

        Returns crew members from the crew table with:
        - id, site, state (idle|busy|down|draining)
        - resources: parsed resources_json
        - capabilities: parsed capabilities
        - current_ticket, last_heartbeat
        - health: parsed health_json (may be null if never set)
        """
        home = resolve_home()
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
    def get_leases(host: str | None = None) -> list[dict[str, Any]]:
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

        home = resolve_home()
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

        home = resolve_home()
        db_path = str(home / "queue.db")
        conn = connect(db_path)
        try:
            # Reuse events.since with optional kind filter
            return events.since(conn, after_id=since, limit=limit, kind=kind)
        finally:
            conn.close()

    @app.get("/api/events/kinds")
    def get_event_kinds() -> list[str]:
        """Get distinct event kinds present in the database.

        Returns a sorted list of event kinds (SELECT DISTINCT kind FROM events ORDER BY kind).
        """
        home = resolve_home()
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
    def get_reductions(run_id: str, phase: str | None = None) -> list[dict[str, Any]]:
        """Get reductions for a run with optional phase filter.

        Returns reductions with parsed json, de-duplicated member_ticket_ids
        (union of json.member_ticket_ids and json.needs_human_ticket_ids),
        and member_tickets with real states from the tickets table.

        Query params:
        - phase: filter to specific phase (optional)

        Returns 404 if run not found.
        """
        home = resolve_home()
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

    @app.websocket("/api/ws")
    async def websocket_endpoint(websocket: WebSocket, since: int = None):
        """WebSocket endpoint for live event stream.

        Polls the real events table and pushes new events to connected clients.

        Query params:
        - since: Start cursor (event id). Default: current max event id (only new events).
                 Use since=0 to replay from start.

        Messages:
        - hello: {type: "hello", last_id: <cursor>} on connect
        - event: {type: "event", event: {...}} for each new event
        """
        await websocket.accept()

        # Get poll interval from env (default 1.0s)
        poll_interval = float(os.environ.get("HERMES_WS_POLL_S", "1.0"))

        # Determine starting cursor: if since is provided use it, else current max event id
        home = resolve_home()
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
            print(f"WebSocket error: {e}")
        finally:
            # Ensure connection is closed
            try:
                await websocket.close()
            except Exception:
                pass

    return app
