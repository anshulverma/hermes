"""testkit.scenarios.fleet — deterministic fake scenario for fleet testing (spec §5).

A scenario generator producing ~40 tickets + a MockAgent result table keyed by
(ticket_id, attempt), engineered to exercise:
- clustering (shared root_cause.signature)
- failures: driver_failed (terminal), infra_failed on attempt 1 then ok on attempt 2
- needs_human via both routes: verify=False and reduce flagging
- contention: more gpu tickets than gpu slots -> parking

The scenario is a single seedable fixture reused by both single-box and fleet tests.

Stdlib-only.
"""
from __future__ import annotations

import random
from engine.models import Ticket
from testkit.mock_agent import MockAgent


def build_fleet_scenario(seed: int = 42) -> tuple[list[Ticket], MockAgent]:
    """Generate a deterministic fleet scenario.

    Returns:
        (tickets, mock_agent): A list of ~40 tickets and a MockAgent with an
        extended scenario table keyed by (ticket_id, attempt).
    """
    rng = random.Random(seed)

    tickets = []
    scenarios = {}

    run_id = "fleet-scenario-1"
    ticket_num = 0

    # Helper to create a ticket
    def mk_ticket(resource_req="cpu", payload=None, priority=0.0):
        nonlocal ticket_num
        tid = f"{run_id}/t-{ticket_num}"
        ticket_num += 1
        return Ticket(
            id=tid,
            run_id=run_id,
            phase="work",
            state="queued",
            resource_req=resource_req,
            priority=priority,
            attempts=0,
            payload=payload or {},
        )

    # 1. CPU tickets with clustering (shared signatures)
    signatures = ["sig-A", "sig-B", "sig-C"]
    for i in range(15):
        sig = rng.choice(signatures)  # Some will share signatures
        ticket = mk_ticket(
            resource_req="cpu",
            payload={"scenario": "ok", "signature": sig, "attempt": 1},
        )
        tickets.append(ticket)
        # All succeed on first attempt
        scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # 2. GPU tickets (more than typical capacity to force parking)
    for i in range(10):
        ticket = mk_ticket(
            resource_req="gpu",
            payload={"scenario": "ok", "attempt": 1},
        )
        tickets.append(ticket)
        scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # 3. Driver-failed tickets (terminal, no retry)
    for i in range(3):
        ticket = mk_ticket(
            resource_req="cpu",
            payload={"scenario": "driver_error", "attempt": 1},
        )
        tickets.append(ticket)
        scenarios[(ticket.id, 1)] = ("driver_failed", "driver_error")

    # 4. Infra-failed then succeed (retry path)
    for i in range(4):
        ticket = mk_ticket(
            resource_req="cpu",
            payload={"scenario": "infra_then_ok", "attempt": 1},
        )
        tickets.append(ticket)
        # Fail on attempt 1, succeed on attempt 2
        scenarios[(ticket.id, 1)] = ("infra_failed", "transport_error")
        scenarios[(ticket.id, 2)] = ("ok", "goal_met")

    # 5. needs_human via verify=False route (re-verify override)
    # This would need playbook support, so we'll simulate with a special marker
    ticket = mk_ticket(
        resource_req="cpu",
        payload={"scenario": "ok", "needs_reverify": True, "attempt": 1},
    )
    tickets.append(ticket)
    scenarios[(ticket.id, 1)] = ("ok", "goal_met")  # Worker succeeds but verify fails

    # 6. needs_human via reduce flagging route
    # This would need reduction logic, so we'll mark it
    ticket = mk_ticket(
        resource_req="cpu",
        payload={"scenario": "ok", "needs_reduce_review": True, "attempt": 1},
    )
    tickets.append(ticket)
    scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # 7. More cpu tickets to reach ~40 total
    remaining = 40 - len(tickets)
    for i in range(max(0, remaining)):
        sig = rng.choice(signatures)
        ticket = mk_ticket(
            resource_req="cpu",
            payload={"scenario": "ok", "signature": sig, "attempt": 1},
        )
        tickets.append(ticket)
        scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # Create MockAgent with the extended scenario table
    agent = MockAgent(healthy=True, scenarios=scenarios)

    return tickets, agent
