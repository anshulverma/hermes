-- Hermes engine core database schema (version 1)
-- From docs/specs/engine-core.md §4
-- SQLite, WAL, synchronous=NORMAL, busy_timeout=5000, foreign_keys=ON, file mode 0600

CREATE TABLE runs (
  id          TEXT PRIMARY KEY,          -- <playbook>-<YYYYMMDD-HHMMSS>
  playbook    TEXT NOT NULL,
  site        TEXT NOT NULL,
  base_ref    TEXT NOT NULL,
  config_json TEXT NOT NULL DEFAULT '{}',
  state       TEXT NOT NULL              -- running|paused|stopped|done|failed
              CHECK(state IN ('running','paused','stopped','done','failed')),
  phase       TEXT,
  created_at  REAL NOT NULL, updated_at REAL NOT NULL
);

CREATE TABLE tickets (
  id           TEXT PRIMARY KEY,         -- <run_id>/t-<n>
  run_id       TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  phase        TEXT NOT NULL,
  state        TEXT NOT NULL             -- see §5 state machine
              CHECK(state IN ('queued','dispatched','running','reducing',
                              'done','parked','failed','needs_human')),
  resource_req TEXT NOT NULL DEFAULT 'cpu',
  priority     REAL NOT NULL DEFAULT 0,
  attempts     INTEGER NOT NULL DEFAULT 0,      -- infra-failure retries only (max 3)
  available_at REAL NOT NULL DEFAULT 0,
  lease_id     TEXT,
  worker_host  TEXT,
  reduction_id INTEGER REFERENCES reductions(id), -- reduction that routed this
                                                --   ticket to needs_human (§5, §9);
                                                --   INTEGER to match reductions.id
                                                --   (FK + §9 lookup require same type)
  tried_hosts  TEXT NOT NULL DEFAULT '[]',      -- JSON array
  payload_json TEXT NOT NULL DEFAULT '{}',      -- playbook payload for this phase
  created_at   REAL NOT NULL, updated_at REAL NOT NULL
);

CREATE TABLE attempts (                          -- append-only audit
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id     TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  phase         TEXT NOT NULL, host TEXT NOT NULL, attempt INTEGER NOT NULL,
  started_at    REAL, ended_at REAL,
  outcome       TEXT,   -- ok|driver_failed|infra_failed  (see §6 Result)
  termination_reason TEXT, -- goal_met|contract_fail|driver_error|timeout|transport_error
  result_ref    TEXT, error_summary TEXT
);

CREATE TABLE findings (                           -- generic per-ticket result doc
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id    TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  ticket_id TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  kind      TEXT NOT NULL, json TEXT NOT NULL, created_at REAL NOT NULL
);

CREATE TABLE reductions (                         -- master-side aggregate output
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id       TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL, json TEXT NOT NULL,
  review_state TEXT NOT NULL DEFAULT 'pending'
              CHECK(review_state IN ('pending','accepted','rejected','superseded')),
  created_at   REAL NOT NULL, updated_at REAL NOT NULL
);

CREATE TABLE crew (
  id             TEXT PRIMARY KEY,        -- host id
  site           TEXT NOT NULL, capabilities TEXT NOT NULL DEFAULT '[]',
  resources_json TEXT NOT NULL DEFAULT '{}',
  state          TEXT NOT NULL            -- idle|busy|down|draining
                CHECK(state IN ('idle','busy','down','draining')),
  health_json    TEXT, current_ticket TEXT, last_heartbeat REAL,
  registered_at  REAL NOT NULL
);

CREATE TABLE leases (
  id            TEXT PRIMARY KEY,
  run_id        TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  resource_class TEXT NOT NULL,
  ticket_id     TEXT, host TEXT,
  acquired_at   REAL NOT NULL, ttl_s INTEGER NOT NULL DEFAULT 1800,
  expires_at    REAL NOT NULL
);

CREATE TABLE events (                             -- append-only feed (§7)
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        REAL NOT NULL, kind TEXT NOT NULL,
  run_id    TEXT, ticket_id TEXT, host TEXT,
  message   TEXT, data_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL, description TEXT);

CREATE INDEX idx_tickets_dispatch ON tickets(run_id, state, available_at, priority);
CREATE INDEX idx_tickets_resource ON tickets(state, resource_req);
CREATE INDEX idx_attempts_ticket ON attempts(ticket_id);
CREATE INDEX idx_events_stream ON events(id);
CREATE INDEX idx_findings_run ON findings(run_id);
