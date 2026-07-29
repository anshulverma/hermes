# Hermes

A standalone engine for running **multi-agent work across a fleet of remote
hosts**, where each "worker" is a headless AI coding agent (Claude Code today;
Codex and others via an agent adapter). Hermes dispatches a **crew** of hosts,
hands out **tickets**, and drives them to a verified result — nothing ships
automatically.

Hermes is **not** a Claude Code plugin. It *uses* an agent runtime to run workers
and *exposes* thin host integrations (a Claude Code plugin under
`integrations/claude-code/`, a Codex launcher later) so a human can start it from
their environment.

## Four extension axes

- **Playbook** — the job (test-fix `mechanic`, training-efficiency `rigger`,
  SEV-RCA `medic`).
- **Site** — the environment/tools (`local` = localhost+git+shell; `meta` =
  devserver with SSH/buck2/sl/testinfra/GPU).
- **Agent** — the worker runtime (`claude`, `codex`, …).
- **Engine** — the generic core that fans work across the crew (queue, dispatch,
  transport, crew+health, leases, contracts, events, control-plane API, CLI).

## Status

The engine core, dexter playbook, local and devserver sites, and control-plane
HTTP API are built and operational. The mechanic and rigger playbooks, codex
agent adapter, and control-plane UI are future work.

Docs:

- `docs/DESIGN.md` — umbrella design (hardened).
- `docs/specs/engine-core.md` + `engine-core-plan.md` — engine core sub-project
  (built).
- `docs/RUNBOOK.md` — operations runbook (deploy, topology, backup, monitoring).
- `docs/specs/federation-future.md` — deferred multi-level federation.
- `web/UI_BRIEF.md` — control-plane UI brief (for Claude Design).

## Quickstart

Create a virtual environment and install Hermes in editable mode with dev and
server extras:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,server]'
```

Run the example playbook on the local site:

```bash
hermes run example --site local
```

Start the control-plane HTTP API server (queues and crew management):

```bash
hermes serve --api
```

Verify configuration and connectivity:

```bash
hermes doctor
```

## Layout

```
engine/  server/  web/  agents/{claude,codex}/  sites/{local,meta}/
playbooks/{mechanic,rigger,medic}/  integrations/{claude-code,codex}/
testkit/  tests/  docs/
```

Runtime data (queue.db, logs, ticket payloads) lives outside the repo under
`HERMES_HOME` (default `~/.hermes`).
