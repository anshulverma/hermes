# hermes:status

Check status of active Hermes runs.

Thin wrapper around `hermes status`.

## Usage

```
/hermes:status [--run <run-id>] [--watch]
```

## Implementation (stub - to be fleshed out in Slice 10)

Shells out to `hermes status` and formats the output for Claude Code display.

Shows:
- Active runs and their states
- Ticket progress (queued/running/done/failed)
- Crew health
- Attention items (needs_human, failures, parked tickets)

Example (future):
```bash
hermes status --run mechanic-20260728-143022
```
