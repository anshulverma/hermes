"""
server.app — FastAPI application.

Minimal control-plane server (Phase A1). Read endpoints over the real queue.db.
"""
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

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

    return app
