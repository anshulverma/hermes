# Hermes Operations Runbook

This runbook covers the operational lifecycle of a Hermes deployment: deploy,
run topology, startup, shutdown, backup, and maintenance.

## Deploy and upgrade

Hermes uses an additive-only migration strategy tracked in the `schema_migrations`
table. Migrations apply automatically on first connection (via `apply_migrations`
in every CLI command that opens the database). The database runs in WAL mode for
concurrent readers.

**Deploy workflow:**

1. Pull the latest code from the repository.
2. Restart the control-plane process and any worker processes.
3. Migrations run automatically on the first connection after restart.

**Migration properties:**

- Additive only (no destructive schema changes).
- Tracked in `schema_migrations` table.
- Idempotent (re-applying is a no-op).
- Database file mode enforced to 0600 on every connection.

## Run topology

A Hermes deployment consists of:

- **One control-plane process** running `hermes serve --api` (the HTTP API
  server for queue and crew management).
- **One master loop** (launched via `hermes run <playbook>`) that owns
  `queue.db` and drives the dispatch and reduction logic.
- **N worker serve loops** (one per host, launched via `hermes serve --host <h>`)
  that poll tickets for their host and execute them.

**Important topology constraints:**

- Only the master loop and the control-plane API share access to `queue.db`.
  Workers never access the queue database directly.
- Workers are reached over the site transport (e.g., SSH for devserver, in-process
  message passing for local). There is no shared database between workers and
  the master.
- The control-plane API server can run on any host with access to `queue.db`.
  For production, run it on the same host as the master loop.

## Starting the control plane and workers

**Start the control-plane API server:**

```bash
hermes serve --api
```

By default, binds to `127.0.0.1:8080`. Override with `--host <bind-address>`
and `--port <port>`.

**Start a worker serve loop:**

```bash
hermes serve --host <hostname> --site <site-name>
```

For example, to run a worker for the local site on localhost:

```bash
hermes serve --host localhost --site local
```

Workers poll the queue for tickets assigned to their host and execute them
using the configured agent.

**Start a run (master loop):**

```bash
hermes run <playbook> --site <site>
```

The master loop seeds tickets, dispatches them to workers, and drives reductions
until the run reaches a terminal state.

## Graceful shutdown and restart

All long-running Hermes processes (master loop, worker serve loops) install
SIGTERM and SIGINT handlers that set a global stop event. When the stop event
is set, the main loop exits cleanly at the next safe boundary, runs a final
heartbeat sweep to requeue in-flight work, logs a graceful shutdown message,
and closes the database.

**systemd integration:**

The example systemd unit at `fleet/hermes-control-plane.service` sets
`TimeoutStopSec=90s` to allow the graceful shutdown pass to complete before
systemd escalates to SIGKILL. This provides ample margin for the final
housekeeping (heartbeat sweep, database close, log flush).

**Manual shutdown:**

Send SIGTERM to the process:

```bash
kill -TERM <pid>
```

Or use systemd:

```bash
systemctl stop hermes-control-plane
```

**Restart workflow:**

For deployments under systemd with `Restart=on-failure`, the service will
restart automatically on non-zero exits. For manual restarts after code
updates, stop the service, pull the new code, and start the service again.
Migrations run automatically on the first connection.

## Token rotation and loss recovery

The control-plane API uses a bearer token stored at `$HERMES_HOME/api_token`
(mode 0600). The token is created automatically on first launch if it does not
exist.

**Rotate the token:**

```bash
hermes serve --api --rotate-token
```

This generates a new token, overwrites `api_token`, and starts the server with
the new token. All clients must update to the new token.

**Loss recovery:**

If the token file is lost or corrupted, the server will generate a new token
on the next launch (if the file is absent) or fail to start (if the file is
corrupted). To force a new token, delete `$HERMES_HOME/api_token` and restart
the server with `--rotate-token`.

**Non-loopback caveat:**

By default, the control-plane API binds to `127.0.0.1` (localhost only). To
expose the API to other hosts, use `--host 0.0.0.0` or a specific interface
address. When binding to a non-loopback address, ensure the token file is
protected (mode 0600) and use HTTPS in production (via a reverse proxy).

## Log configuration and rotation

Hermes uses Python's `logging` module for process diagnostics. Logs are separate
from the events table (events are the queryable audit trail; logs are for
real-time diagnostics).

**Configuration via environment variables:**

- `HERMES_LOG_LEVEL` (default: `INFO`, or `DEBUG` if `HERMES_DEBUG` is truthy)
- `HERMES_LOG_FORMAT` (default: `text`; values: `text` or `json`)
- `HERMES_LOG_FILE` (default: unset, logs to stderr)

**JSON logs for structured shipping:**

Set `HERMES_LOG_FORMAT=json` to emit structured JSON logs (one JSON object per
line). Use this mode when shipping logs to a centralized aggregator (e.g.,
Splunk, Datadog, ELK).

**Log rotation:**

Hermes does not perform in-process log rotation. Use OS-level log rotation:

- **systemd/journald:** Logs are captured by journald when `HERMES_LOG_FILE` is
  unset (stderr). Configure journal retention via `journald.conf`.
- **logrotate:** When `HERMES_LOG_FILE` is set to a file path, use `logrotate`
  to rotate the file. Example `logrotate.d` snippet:

```
/var/log/hermes/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0600 hermes hermes
    sharedscripts
    postrotate
        systemctl reload hermes-control-plane
    endscript
}
```

- **Container runtimes:** When running in a container, configure the container
  runtime's log driver (e.g., Docker's `json-file` driver with `max-size` and
  `max-file` options).

## Backup and restore

Hermes uses SQLite with WAL mode. Online backups can be taken while the database
is live using the `VACUUM INTO` command.

**Create an online backup:**

```bash
hermes db backup --output /path/to/backup.db
```

This creates a copy of `queue.db` at the specified path without locking the
live database.

**Restore workflow:**

1. Stop all processes (control-plane server, master loop, workers).
2. Replace `queue.db` with the backup file.
3. Remove stale WAL and SHM files: `rm -f queue.db-wal queue.db-shm`.
4. Restart the processes.

**Backup cadence:**

For production deployments, back up `queue.db` at least daily. Store backups
off-host or in a separate volume. Retention depends on your operational needs
(e.g., 7 days of dailies, 4 weeks of weeklies).

## Prune and vacuum cadence

Hermes accumulates events and attempts in unbounded-growth tables. Prune old
events and attempts periodically to keep the database size manageable.

**Prune old events and attempts:**

```bash
hermes db prune --events-days 90 --attempts-days 90
```

This deletes events and attempts older than 90 days, but only for terminal
tickets and runs. In-flight work is never pruned.

**Vacuum to reclaim space:**

After pruning, vacuum the database to reclaim disk space:

```bash
hermes db vacuum
```

**Recommended cadence:**

- Prune weekly or monthly, depending on event volume.
- Vacuum after each prune to reclaim space.
- Run prune during low-traffic windows (though it is safe to run while the
  database is live, it may increase I/O contention).

## Doctor diagnostics

The `hermes doctor` command is the first diagnostic step when troubleshooting
configuration or connectivity issues. It runs all startup validation checks in
read-only mode and reports on:

- `HERMES_HOME` resolution and writability.
- `queue.db` connectivity and schema version.
- Log configuration (`HERMES_LOG_LEVEL`, `HERMES_LOG_FORMAT`, `HERMES_LOG_FILE`).
- Server dependencies (if `[server]` extras are installed).

**Run doctor:**

```bash
hermes doctor
```

**Example output:**

```
HERMES_HOME: /home/user/.hermes (writable)
queue.db: connected (version 1)
Logging: level=INFO, format=text, file=stderr
Server dependencies: installed
```

If any checks fail, `hermes doctor` reports the issue and exits with a non-zero
code. Fix configuration issues before starting the control plane or workers.
