# Hermes Skill

Guide Claude Code through running multi-agent fleet work with Hermes.

## When to use

Use this skill when the user wants to:
- Run a playbook across a fleet of AI agents
- Manage Hermes crew members (add/remove/drain hosts)
- Check status of active runs
- Investigate tickets, reductions, or attention items

## Workflow

### Starting a run

1. **Choose the playbook** - `mechanic` (test-fix), `rigger` (efficiency), etc.
2. **Select the site** - `local` (localhost), `meta` (devserver+SSH), etc.
3. **Dry-run first** - Always use `--dry-run` to preview before dispatching real work
4. **Start the run** - Remove `--dry-run` to actually dispatch

Example:
```bash
# Preview
hermes run mechanic --site local --dry-run

# Execute
hermes run mechanic --site local
```

### Monitoring progress

Use `hermes status` to watch the run:

```bash
# Watch mode (updates in real-time)
hermes status --run mechanic-20260728-143022 --watch

# One-shot
hermes status
```

### Managing crew

Before starting work, ensure the crew is healthy:

```bash
# List current crew
hermes crew list --site local

# Add a host (provisions + health-checks)
hermes crew add worker-1 --site local
```

## Implementation note

This is a stub skill. Full orchestration logic (handling failures, needs_human decisions, reduction review, etc.) will be fleshed out in Slice 10 when the CLI is complete.
