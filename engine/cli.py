"""CLI entrypoint for Hermes engine.

Thin wrappers over engine modules. Stdlib-only (argparse).
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from engine import config, crew, playbook, site, agent, queue, dispatch, log, shutdown
from engine.db import migrate
from engine.models import Run


def _connect():
    """Connect to queue.db (applying migrations if needed)."""
    home = config.resolve_home()
    db_path = home / "queue.db"
    migrate.apply_migrations(str(db_path))
    return migrate.connect(str(db_path))


def _load_playbook_site_agent(args):
    """Load and return (playbook, site, agent) from args and registries.

    Imports the registration modules first. Returns None for playbook if
    args has no playbook attribute (callers that discard it are unaffected).
    """
    # Import production modules unconditionally
    import sites.local.site
    import playbooks.dexter
    import sites.devserver.site
    import agents.claude

    # Import testkit modules only when needed
    playbook_name = getattr(args, 'playbook', None)
    if playbook_name == "example":
        import testkit.example_playbook

    ag_name = getattr(args, 'agent', None) or config.agent()
    if ag_name == "mock":
        import testkit.mock_agent

    pb = playbook.load(playbook_name) if playbook_name else None
    st = site.load(args.site)
    ag = agent.load(ag_name)
    return pb, st, ag


def _load_goals_file(path):
    """Load goals from a file.

    Format:
    - One goal per line
    - Skip blank lines
    - Skip lines whose first non-space char is '#'
    - Strip surrounding whitespace on each kept line

    Returns:
        list[str]: Parsed goals in order (empty list if file doesn't exist)
    """
    goals = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                # Skip blank lines
                if not stripped:
                    continue
                # Skip comment lines (first non-space char is '#')
                if stripped.startswith('#'):
                    continue
                goals.append(stripped)
    except FileNotFoundError:
        return []
    return goals


def _create_run(conn, playbook_name, site_name, base_ref, run_config=None):
    """Create a new run row and return its ID."""
    run_id = f"run-{int(time.time() * 1000)}"
    now = time.time()
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'running', NULL, ?, ?)""",
        (run_id, playbook_name, site_name, base_ref,
         json.dumps(run_config or {}), now, now),
    )
    conn.commit()
    return run_id


def cmd_run(args):
    """hermes run <playbook> --site <site> [--agent <agent>] [--dry-run] [--base-ref R] [--goals FILE]."""
    # Install SIGTERM/SIGINT handlers for graceful shutdown
    shutdown.install_handlers()

    pb, st, ag = _load_playbook_site_agent(args)

    conn = _connect()
    base_ref = getattr(args, 'base_ref', None) or 'main'

    # Build run_config from --goals if provided
    run_config = {}
    if hasattr(args, 'goals') and args.goals:
        goals = _load_goals_file(args.goals)
        run_config = {"goals": goals}

    # Create run
    run_id = _create_run(conn, pb.name, st.name, base_ref, run_config)

    # Set the initial phase (phase 0)
    initial_phase = pb.phases[0]
    queue.set_run_phase(conn, run_id, initial_phase)

    # Load the run
    run_row = conn.execute(
        """SELECT id, playbook, site, base_ref, config_json, phase
           FROM runs WHERE id=?""",
        (run_id,),
    ).fetchone()
    run = Run(
        id=run_row[0],
        playbook=run_row[1],
        site=run_row[2],
        base_ref=run_row[3],
        config=json.loads(run_row[4]),
        phase=run_row[5],
        reductions=[],
    )

    # Seed the initial phase
    tickets = queue.seed_tickets(conn, run, pb, st)

    if args.dry_run:
        # Dry-run: print report, no dispatch
        print(f"Run {run_id} created (dry-run mode)")
        print(f"Seeded {len(tickets)} tickets:")
        for t in tickets:
            print(f"  {t.id} (phase={t.phase}, priority={t.priority})")
        conn.close()
        return 0

    # Non-dry-run: drive to terminal via master_loop
    print(f"Run {run_id} starting (local mode)...")

    # Determine hosts (for local site, use the local host)
    hosts = getattr(args, 'hosts', None)
    if not hosts:
        # Default: for local site, use localhost
        hosts = ['localhost']
    elif isinstance(hosts, str):
        hosts = [h.strip() for h in hosts.split(',')]

    # Add hosts to crew (for local in-process serving)
    for host in hosts:
        try:
            crew.add(conn, st, ag, host, base_ref)
        except ValueError as e:
            # Host failed health check
            print(f"Error adding host {host}: {e}", file=sys.stderr)
            conn.close()
            return 1

    # For local site, drive master_loop which launches in-process serve loops
    dispatch.master_loop(
        conn=conn,
        run_id=run_id,
        playbook=pb,
        site=st,
        agent=ag,
        base_ref=base_ref,
        hosts=hosts,
        max_cycles=1000,  # bounded to avoid infinite loops
    )

    # Log graceful shutdown if the stop flag was set
    if shutdown.stop_event.is_set():
        shutdown.log_graceful_shutdown()

    # Check final state
    final_state = conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]
    print(f"Run {run_id} finished: {final_state}")
    conn.close()
    return 0


def cmd_run_control(args):
    """hermes run {pause|resume|stop} <run_id>."""
    action = args.action
    run_id = args.run_id

    conn = _connect()

    # Map action to state
    state_map = {
        'pause': 'paused',
        'resume': 'running',
        'stop': 'stopped',
    }
    new_state = state_map[action]

    try:
        queue.set_run_state(conn, run_id, new_state)
        final_state = conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        print(f"Run {run_id}: {final_state}")
        conn.close()
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        conn.close()
        return 1


def cmd_reduction(args):
    """hermes reduction {accept|reject} <reduction_id>."""
    action = args.action
    reduction_id = int(args.reduction_id)

    conn = _connect()

    if action == 'accept':
        queue.accept_reduction(conn, reduction_id)
        print(f"Reduction {reduction_id}: accepted")
    elif action == 'reject':
        queue.reject_reduction(conn, reduction_id)
        print(f"Reduction {reduction_id}: rejected")

    conn.close()
    return 0


def cmd_ticket_requeue(args):
    """hermes ticket requeue <ticket_id>."""
    ticket_id = args.ticket_id

    conn = _connect()
    queue.requeue_needs_human(conn, ticket_id)
    print(f"Ticket {ticket_id}: requeued")
    conn.close()
    return 0


def cmd_crew_add(args):
    """hermes crew add <host> --site <site> [--agent <agent>]."""
    _, st, ag = _load_playbook_site_agent(args)
    host = args.host
    base_ref = getattr(args, 'base_ref', None) or 'main'

    conn = _connect()

    try:
        crew.add(conn, st, ag, host, base_ref)
        print(f"Host {host}: healthy, admitted to crew")
        conn.close()
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        conn.close()
        return 1


def cmd_crew_list(args):
    """hermes crew list --site <site>."""
    conn = _connect()

    rows = conn.execute(
        "SELECT id, site, state, resources_json FROM crew ORDER BY id"
    ).fetchall()

    if not rows:
        print("No crew members")
    else:
        print(f"{'Host':<20} {'Site':<10} {'State':<10} Resources")
        print("-" * 60)
        for row in rows:
            host, site_name, state, resources_json = row
            resources = json.loads(resources_json)
            res_str = ", ".join(f"{k}={v}" for k, v in resources.items())
            print(f"{host:<20} {site_name:<10} {state:<10} {res_str}")

    conn.close()
    return 0


def cmd_status(args):
    """hermes status [--run R] [--watch]."""
    conn = _connect()

    # Filter by run if specified
    run_filter = getattr(args, 'run', None)

    # Runs
    if run_filter:
        runs = conn.execute(
            "SELECT id, playbook, site, state, phase FROM runs WHERE id=?",
            (run_filter,)
        ).fetchall()
    else:
        runs = conn.execute(
            "SELECT id, playbook, site, state, phase FROM runs ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

    print("=== Runs ===")
    if not runs:
        print("  (none)")
    else:
        for run_id, pb, st, state, phase in runs:
            print(f"  {run_id}: {state} (playbook={pb}, site={st}, phase={phase})")

    # Tickets (if run filter)
    if run_filter:
        tickets = conn.execute(
            "SELECT id, phase, state FROM tickets WHERE run_id=? ORDER BY phase, priority DESC LIMIT 20",
            (run_filter,)
        ).fetchall()
        print("\n=== Tickets ===")
        if not tickets:
            print("  (none)")
        else:
            for tid, phase, state in tickets:
                print(f"  {tid}: {state} (phase={phase})")

    # Crew
    crew_count = conn.execute("SELECT COUNT(*) FROM crew").fetchone()[0]
    print(f"\n=== Crew: {crew_count} members ===")

    # Leases
    lease_count = conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0]
    print(f"\n=== Leases: {lease_count} active ===")

    # needs_human attention
    needs_human = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE state='needs_human'"
    ).fetchone()[0]
    if needs_human > 0:
        print(f"\n⚠️  Attention: {needs_human} tickets need human review")

    conn.close()
    return 0


def cmd_show(args):
    """hermes show <ticket_id>."""
    ticket_id = args.ticket_id

    conn = _connect()

    # Ticket
    ticket = conn.execute(
        """SELECT id, run_id, phase, state, resource_req, priority, attempts,
                  payload_json, tried_hosts, reduction_id
           FROM tickets WHERE id=?""",
        (ticket_id,)
    ).fetchone()

    if not ticket:
        print(f"Ticket {ticket_id} not found", file=sys.stderr)
        conn.close()
        return 1

    tid, run_id, phase, state, resource_req, priority, attempts, payload_json, tried_hosts, reduction_id = ticket
    payload = json.loads(payload_json)
    tried = json.loads(tried_hosts)

    print(f"=== Ticket {tid} ===")
    print(f"Run: {run_id}")
    print(f"Phase: {phase}")
    print(f"State: {state}")
    print(f"Resource: {resource_req}")
    print(f"Priority: {priority}")
    print(f"Attempts: {attempts}")
    print(f"Tried hosts: {tried}")
    if reduction_id:
        print(f"Reduction: {reduction_id}")
    print(f"\nPayload:")
    print(json.dumps(payload, indent=2))

    # Attempts
    attempt_rows = conn.execute(
        """SELECT host, attempt, started_at, ended_at, outcome, termination_reason, error_summary
           FROM attempts WHERE ticket_id=? ORDER BY attempt""",
        (ticket_id,)
    ).fetchall()

    if attempt_rows:
        print(f"\n=== Attempts ({len(attempt_rows)}) ===")
        for host, attempt, started, ended, outcome, term_reason, error in attempt_rows:
            duration = (ended - started) if (started and ended) else None
            print(f"  Attempt {attempt} on {host}: {outcome} ({term_reason})")
            if duration:
                print(f"    Duration: {duration:.2f}s")
            if error:
                print(f"    Error: {error}")

    # Result (if exists in ticket envelope)
    # For simplicity, we show the last attempt's result (already shown above)

    conn.close()
    return 0


def cmd_serve_api(args):
    """hermes serve --api [--host 127.0.0.1] [--port 8080] [--rotate-token].

    Run the FastAPI control-plane server. Thin wrapper around uvicorn.
    """
    try:
        import uvicorn
        from server.app import create_app
        from server.auth import rotate_token
    except ImportError as e:
        print(f"Error: server dependencies not installed. Run: pip install -e '.[server]'", file=sys.stderr)
        print(f"  ({e})", file=sys.stderr)
        return 1

    home = config.resolve_home()

    # Rotate token if requested
    if getattr(args, 'rotate_token', False):
        rotate_token(home)
        print(f"Token rotated (stored at {home / 'api_token'})")

    # Get bind from args or config.bind()
    bind = args.host or config.bind()
    port = args.port

    # Create the app with bind
    app = create_app(bind=bind)

    print(f"Starting Hermes API server on http://{bind}:{port}")
    print(f"HERMES_HOME: {home}")
    print(f"Token location: {home / 'api_token'}")

    # Run uvicorn (host param for uvicorn is where to listen)
    uvicorn.run(app, host=bind, port=port, log_level="info")
    return 0


def cmd_serve(args):
    """hermes serve --host <h> --site <site> [--agent <agent>] [--run R] OR --api [--host H] [--port P]."""
    # API server mode
    if args.api:
        # Additional validation for API server: require server dependencies
        try:
            config.validate_startup(require_server=True)
        except config.ConfigError as e:
            logger = log.get_logger("cli")
            logger.error("Configuration error: %s", e)
            return 1
        return cmd_serve_api(args)

    # Worker mode (original behavior) - install SIGTERM/SIGINT handlers
    shutdown.install_handlers()

    _, st, ag = _load_playbook_site_agent(args)
    host = args.host
    if not host:
        print("Error: --host is required for worker mode", file=sys.stderr)
        return 1
    if not args.site:
        print("Error: --site is required for worker mode", file=sys.stderr)
        return 1
    base_ref = getattr(args, 'base_ref', None) or 'main'

    conn = _connect()

    # Determine which run to serve (explicit --run or the single active/most-recent running run)
    run_id = getattr(args, 'run', None)
    if not run_id:
        # Find the most recent running run
        row = conn.execute(
            """SELECT id FROM runs WHERE state='running'
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        if not row:
            print("Error: no running run found (specify --run <run_id>)", file=sys.stderr)
            conn.close()
            return 1
        run_id = row[0]

    # Load the run
    run_row = conn.execute(
        """SELECT id, playbook, site, base_ref, config_json, phase
           FROM runs WHERE id=?""",
        (run_id,),
    ).fetchone()
    if not run_row:
        print(f"Error: run {run_id} not found", file=sys.stderr)
        conn.close()
        return 1

    run = Run(
        id=run_row[0],
        playbook=run_row[1],
        site=run_row[2],
        base_ref=run_row[3],
        config=json.loads(run_row[4]),
        phase=run_row[5],
        reductions=[],
    )

    # Resolve the playbook from the run's stored playbook name
    playbook_name = run.playbook
    if playbook_name == "example":
        import testkit.example_playbook
    pb = playbook.load(playbook_name)

    # TODO(dexter): --goals FILE seeding

    # Run the serve loop (bounded — serve available work then return)
    processed = dispatch.serve_loop(conn, st, ag, host, run, pb, base_ref)

    # Log graceful shutdown if the stop flag was set
    if shutdown.stop_event.is_set():
        shutdown.log_graceful_shutdown()

    print(f"Host {host}: processed {processed} tickets for run {run_id}")
    conn.close()
    return 0


def cmd_serve_once(args):
    """hermes serve-once --envelope PATH --result PATH --timeout N.

    Worker-runner: reads envelope, loads agent, builds invocation, runs under timeout,
    writes result. Agent-agnostic. Used by ssh_transport on fleet workers.
    """
    import subprocess
    import shutil

    envelope_path = args.envelope
    result_path = args.result
    timeout_s = args.timeout

    # 1. Read + parse the envelope
    try:
        with open(envelope_path) as f:
            envelope = json.load(f)
    except FileNotFoundError:
        print(f"Error: envelope file not found: {envelope_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in envelope: {e}", file=sys.stderr)
        return 1

    # 2. Load the agent via HERMES_AGENT (default claude). Register the requested
    #    adapter via import side-effect: agents.claude for production; testkit's
    #    MockAgent only for the mock path (production serve-once does not depend on
    #    the test-only testkit package).
    agent_name = config.agent()  # reads HERMES_AGENT, defaults to "claude"
    if agent_name == "mock":
        import testkit.mock_agent  # noqa: F401  (registers "mock")
    else:
        import agents.claude  # noqa: F401  (registers "claude")
    try:
        ag = agent.load(agent_name)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # 3. Reconstruct the Driver from envelope["goal_envelope"]["driver"]
    from engine.models import Driver
    d = envelope["goal_envelope"]["driver"]
    driver = Driver(command=d.get("command"), args=d.get("args", {}), loop=d.get("loop"))

    # 4. Build invocation and run under timeout wrapper
    argv = ag.build_invocation(envelope, driver)

    timeout_bin = shutil.which("timeout")
    wrapped = [timeout_bin, str(timeout_s), *argv] if timeout_bin else list(argv)

    try:
        proc = subprocess.run(wrapped, capture_output=True, text=True)
    except OSError as exc:
        print(f"Error: failed to launch worker: {exc}", file=sys.stderr)
        return 1

    # Write the worker's raw stdout to the result file. The master reads this file
    # and calls agent.parse_result on the raw content to reconstruct the Result.
    try:
        with open(result_path, "w") as f:
            f.write(proc.stdout or "")
    except OSError as exc:
        print(f"Error: failed to write result file: {exc}", file=sys.stderr)
        return 1

    # Exit with the subprocess's exit code
    return 0 if proc.returncode == 0 else 1


def cmd_doctor(args):
    """hermes doctor / hermes config check: read-only config diagnostics.

    Reports resolved configuration + problems. Exits 0 all-clear, 1 on hard problems.
    NEVER prints secret values (secrets shown as set/unset).
    """
    import stat as stat_module

    problems = []

    # Secret env var keys (never print values, only set/unset)
    SECRET_KEYS = {
        'HERMES_SSH_IDENTITY',  # prefix match
        'HERMES_AUTHORIZED_KEY',
        'api_token',
    }

    def is_secret(key):
        """Check if a key name indicates a secret."""
        for secret in SECRET_KEYS:
            if secret in key:
                return True
        return False

    def redact_value(key, value):
        """Redact secret values, return 'set' or 'unset'."""
        if is_secret(key):
            return 'set' if value else 'unset'
        return value if value else 'unset'

    # 1. Resolve HERMES_HOME + networked guard
    print("=== HERMES_HOME ===")
    try:
        home = config.resolve_home()
        print(f"  Path: {home}")
        print(f"  Networked FS guard: passed")
    except config.ConfigError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        problems.append(f"HERMES_HOME: {e}")
        return 1  # Hard problem, exit immediately

    # 2. queue.db: path, existence, mode, migration version(s)
    print("\n=== queue.db ===")
    db_path = home / "queue.db"
    print(f"  Path: {db_path}")

    if db_path.exists():
        print(f"  Exists: yes")
        try:
            file_stat = db_path.stat()
            file_mode = stat_module.S_IMODE(file_stat.st_mode)
            print(f"  Mode: {oct(file_mode)}")

            # Check migration versions
            conn = migrate.connect(str(db_path))
            try:
                versions = conn.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
                if versions:
                    version_list = [str(v[0]) for v in versions]
                    print(f"  Migrations applied: {', '.join(version_list)}")
                else:
                    print(f"  Migrations applied: none")
            except Exception as e:
                print(f"  ERROR reading migrations: {e}", file=sys.stderr)
                problems.append(f"queue.db: cannot read migrations: {e}")
            finally:
                conn.close()
        except PermissionError as e:
            print(f"  ERROR: unreadable ({e})", file=sys.stderr)
            problems.append(f"queue.db: unreadable")
    else:
        print(f"  Exists: no (will be created on first use)")

    # 3. api_token: path, mode (NEVER the value)
    print("\n=== api_token ===")
    token_path = home / "api_token"
    print(f"  Path: {token_path}")

    if token_path.exists():
        print(f"  Exists: yes")
        try:
            file_stat = token_path.stat()
            file_mode = stat_module.S_IMODE(file_stat.st_mode)
            print(f"  Mode: {oct(file_mode)}")
            print(f"  Value: set (redacted)")
        except PermissionError as e:
            print(f"  ERROR: unreadable ({e})", file=sys.stderr)
    else:
        print(f"  Exists: no (will be created on first API access)")

    # 4. Resolved config vars
    print("\n=== Configuration ===")
    print(f"  HERMES_SITE: {config.site()}")
    print(f"  HERMES_AGENT: {config.agent()}")
    print(f"  HERMES_HEARTBEAT_S: {config.heartbeat_s()}")
    print(f"  HERMES_BIND: {config.bind()}")
    print(f"  HERMES_LOG_LEVEL: {config.log_level()}")
    print(f"  HERMES_LOG_FORMAT: {config.log_format()}")
    log_file_val = config.log_file()
    print(f"  HERMES_LOG_FILE: {log_file_val if log_file_val else 'stderr'}")

    # Report all KNOWN_VARS (effective values, secrets redacted)
    print("\n=== Environment Variables ===")
    for var_name, var_desc in sorted(config.KNOWN_VARS.items()):
        # Skip dynamic suffixed vars (they have <...> in the name)
        if '<' in var_name:
            continue

        env_value = os.environ.get(var_name)
        display_value = redact_value(var_name, env_value)
        print(f"  {var_name}: {display_value}")

    # Check for dynamic SSH identity vars (HERMES_SSH_IDENTITY_<host>)
    ssh_identity_keys = [k for k in os.environ if k.startswith('HERMES_SSH_IDENTITY_')]
    if ssh_identity_keys:
        print("\n=== SSH Identities (per-host) ===")
        for key in sorted(ssh_identity_keys):
            print(f"  {key}: set (redacted)")

    # 5. Site/agent adapter load check (if --site/--agent specified)
    if hasattr(args, 'site') and args.site:
        print(f"\n=== Site Adapter: {args.site} ===")
        try:
            # Import production modules
            import sites.local.site
            import sites.devserver.site
            st = site.load(args.site)
            print(f"  Loads: yes (name={st.name})")
        except KeyError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            problems.append(f"Site {args.site}: unresolvable")

    if hasattr(args, 'agent') and args.agent:
        print(f"\n=== Agent Adapter: {args.agent} ===")
        try:
            # Import production modules
            import agents.claude
            import testkit.mock_agent
            ag = agent.load(args.agent)
            print(f"  Loads: yes (name={ag.name})")
        except KeyError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            problems.append(f"Agent {args.agent}: unresolvable")

    # If no specific site/agent, check that registered adapters load
    if not (hasattr(args, 'site') and args.site):
        print("\n=== Registered Site Adapters ===")
        try:
            import sites.local.site
            import sites.devserver.site
            # List registered sites
            from engine.site import _REGISTRY as site_registry
            for site_name in sorted(site_registry.keys()):
                print(f"  {site_name}: registered")
        except Exception as e:
            print(f"  ERROR loading site modules: {e}", file=sys.stderr)

    if not (hasattr(args, 'agent') and args.agent):
        print("\n=== Registered Agent Adapters ===")
        try:
            import agents.claude
            import testkit.mock_agent
            # List registered agents
            from engine.agent import _REGISTRY as agent_registry
            for agent_name in sorted(agent_registry.keys()):
                print(f"  {agent_name}: registered")
        except Exception as e:
            print(f"  ERROR loading agent modules: {e}", file=sys.stderr)

    # 6. Server extra check (fastapi/uvicorn)
    print("\n=== Server Extra ===")
    try:
        import fastapi
        import uvicorn
        print(f"  fastapi: importable")
        print(f"  uvicorn: importable")
    except ImportError as e:
        print(f"  Server dependencies: not installed (pip install -e '.[server]')")

    # Exit code
    if problems:
        print(f"\n=== Problems ({len(problems)}) ===", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("\n✓ All checks passed")
    return 0


def cmd_crew(args):
    """Dispatch crew subcommands."""
    subcommand = args.crew_action

    if subcommand == 'add':
        return cmd_crew_add(args)
    elif subcommand == 'list':
        return cmd_crew_list(args)
    elif subcommand in ('drain', 'remove'):
        print(f"crew {subcommand} not yet implemented", file=sys.stderr)
        return 1
    else:
        print(f"Unknown crew action: {subcommand}", file=sys.stderr)
        return 1


def main(argv=None):
    """Main CLI entrypoint.

    Args:
        argv: Optional list of command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 = success, non-zero = error)
    """
    # Validate startup config before logging (to catch invalid log config early)
    try:
        config.validate_startup()
    except config.ConfigError as e:
        # Log to stderr directly since logging not configured yet
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Configure logging once at entry
    log.configure()

    parser = argparse.ArgumentParser(
        prog='hermes',
        description='Hermes engine CLI'
    )
    subparsers = parser.add_subparsers(dest='command', help='Subcommands')

    # --- run ---
    # We can't use subparsers for "run" because we need to support both:
    # - run <playbook> --site ...
    # - run pause <run_id>
    # So we'll use a first positional arg to disambiguate
    run_parser = subparsers.add_parser('run', help='Run a playbook or control a run')
    run_parser.add_argument('action_or_playbook', help='pause/resume/stop or playbook name')
    run_parser.add_argument('run_id_or_site', nargs='?', help='Run ID (for control) or ignored')
    run_parser.add_argument('--site', help='Site name (for run playbook)')
    run_parser.add_argument('--agent', help='Agent name (default: HERMES_AGENT)')
    run_parser.add_argument('--base-ref', help='Base ref (default: main)')
    run_parser.add_argument('--hosts', help='Comma-separated hosts (default: localhost for local site)')
    run_parser.add_argument('--goals', help='Path to goals file (one goal per line, # for comments)')
    run_parser.add_argument('--dry-run', action='store_true', help='Seed only, no dispatch')

    # --- reduction ---
    red_parser = subparsers.add_parser('reduction', help='Reduction control')
    red_subparsers = red_parser.add_subparsers(dest='action')
    red_accept = red_subparsers.add_parser('accept')
    red_accept.add_argument('reduction_id', help='Reduction ID')
    red_reject = red_subparsers.add_parser('reject')
    red_reject.add_argument('reduction_id', help='Reduction ID')

    # --- ticket ---
    ticket_parser = subparsers.add_parser('ticket', help='Ticket control')
    ticket_subparsers = ticket_parser.add_subparsers(dest='ticket_action')
    ticket_requeue = ticket_subparsers.add_parser('requeue')
    ticket_requeue.add_argument('ticket_id', help='Ticket ID')

    # --- crew ---
    crew_parser = subparsers.add_parser('crew', help='Crew management')
    crew_subparsers = crew_parser.add_subparsers(dest='crew_action')
    crew_add = crew_subparsers.add_parser('add')
    crew_add.add_argument('host', help='Host to add')
    crew_add.add_argument('--site', required=True, help='Site name')
    crew_add.add_argument('--agent', help='Agent name')
    crew_add.add_argument('--base-ref', help='Base ref (default: main)')

    crew_list = crew_subparsers.add_parser('list')
    crew_list.add_argument('--site', required=True, help='Site name')

    # --- status ---
    status_parser = subparsers.add_parser('status', help='Show status')
    status_parser.add_argument('--run', help='Filter to specific run')
    status_parser.add_argument('--watch', action='store_true', help='Watch mode (not implemented)')

    # --- show ---
    show_parser = subparsers.add_parser('show', help='Show ticket details')
    show_parser.add_argument('ticket_id', help='Ticket ID')

    # --- serve ---
    serve_parser = subparsers.add_parser('serve', help='Run serve loop for a host or API server')
    serve_parser.add_argument('--api', action='store_true', help='Run the API server')
    serve_parser.add_argument('--host', help='Host to serve (for worker) or bind address (for API)')
    serve_parser.add_argument('--port', type=int, default=8080, help='Port for API server (default: 8080)')
    serve_parser.add_argument('--rotate-token', action='store_true', help='Rotate API token before starting (API mode only)')
    serve_parser.add_argument('--site', help='Site name (for worker)')
    serve_parser.add_argument('--agent', help='Agent name (for worker)')
    serve_parser.add_argument('--run', help='Run ID (for worker, default: most recent running run)')
    serve_parser.add_argument('--base-ref', help='Base ref (for worker, default: main)')

    # --- serve-once ---
    serve_once_parser = subparsers.add_parser('serve-once', help='Worker-runner: run one agent invocation (used by fleet)')
    serve_once_parser.add_argument('--envelope', required=True, help='Path to envelope.json')
    serve_once_parser.add_argument('--result', required=True, help='Path to write result output')
    serve_once_parser.add_argument('--timeout', type=int, required=True, help='Timeout in seconds')

    # --- doctor ---
    doctor_parser = subparsers.add_parser('doctor', help='Read-only config diagnostics')
    doctor_parser.add_argument('--site', help='Specific site to check')
    doctor_parser.add_argument('--agent', help='Specific agent to check')

    # --- config ---
    config_parser = subparsers.add_parser('config', help='Configuration management')
    config_subparsers = config_parser.add_subparsers(dest='config_action')
    config_check = config_subparsers.add_parser('check', help='Read-only config diagnostics (alias for doctor)')
    config_check.add_argument('--site', help='Specific site to check')
    config_check.add_argument('--agent', help='Specific agent to check')

    # Parse
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    # Dispatch
    try:
        if args.command == 'run':
            # Disambiguate: is first arg a control action or a playbook?
            if args.action_or_playbook in ('pause', 'resume', 'stop'):
                # run control
                args.action = args.action_or_playbook
                args.run_id = args.run_id_or_site
                if not args.run_id:
                    print(f"Error: run {args.action} requires <run_id>", file=sys.stderr)
                    return 1
                return cmd_run_control(args)
            else:
                # run <playbook> ... (requires --site)
                args.playbook = args.action_or_playbook
                if not args.site:
                    print("Error: --site is required for 'hermes run <playbook>'", file=sys.stderr)
                    return 1
                return cmd_run(args)
        elif args.command == 'reduction':
            return cmd_reduction(args)
        elif args.command == 'ticket':
            if args.ticket_action == 'requeue':
                return cmd_ticket_requeue(args)
        elif args.command == 'crew':
            return cmd_crew(args)
        elif args.command == 'status':
            return cmd_status(args)
        elif args.command == 'show':
            return cmd_show(args)
        elif args.command == 'serve':
            return cmd_serve(args)
        elif args.command == 'serve-once':
            return cmd_serve_once(args)
        elif args.command == 'doctor':
            return cmd_doctor(args)
        elif args.command == 'config':
            if args.config_action == 'check':
                return cmd_doctor(args)
    except Exception as e:
        logger = log.get_logger("cli")
        # Use logger.exception when config.debug() is set (includes traceback),
        # otherwise logger.error (message only)
        if config.debug():
            logger.exception("Command failed: %s", e)
        else:
            logger.error("Command failed: %s", e)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
