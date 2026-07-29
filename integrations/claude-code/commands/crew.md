# hermes:crew

Manage the Hermes crew (worker hosts).

Thin wrapper around `hermes crew`.

## Usage

```
/hermes:crew {add|remove|drain|list} [host] [--site <site>]
```

## Implementation (stub - to be fleshed out in Slice 10)

Shells out to `hermes crew` for crew management operations.

Operations:
- `add <host>`: Provision, health-check, and add a host to the crew
- `remove <host>`: Remove a host from the crew
- `drain <host>`: Stop dispatching new work to a host (graceful removal)
- `list`: Show all crew members and their states

Example (future):
```bash
hermes crew add worker-1 --site local
hermes crew list --site local
```
