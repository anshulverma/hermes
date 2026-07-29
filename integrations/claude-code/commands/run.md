# hermes:run

Start a Hermes run.

Thin wrapper around the `hermes` CLI. Shells out to run a playbook across the configured fleet.

## Usage

```
/hermes:run <playbook> [--site <site>] [--base-ref <ref>] [--dry-run]
```

## Implementation (stub - to be fleshed out in Slice 10)

For now, this is a placeholder. The full implementation will:
1. Parse arguments
2. Shell out to: `hermes run <playbook> --site <site> [...]`
3. Stream output back to the user
4. Provide real-time status updates via `hermes status --watch`

Example (future):
```bash
hermes run mechanic --site local --dry-run
```
