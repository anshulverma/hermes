"""Fleet integration test scenario generator. Produces 40 tickets exercising clustering, retries, parking, and needs_human routes."""
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

    # Helper to create a ticket. Every payload carries ``root_cause.signature``
    # (the reduce clustering key); a flat ``signature`` mirror is kept for the
    # lightweight scenario-shape unit tests. ``attempt`` is informational only —
    # the MockAgent derives the real attempt from execution order, not the
    # payload (payloads are static across engine retries).
    def mk_ticket(resource_req="cpu", *, signature, scenario="ok", extra=None,
                  priority=0.0):
        nonlocal ticket_num
        tid = f"{run_id}/t-{ticket_num}"
        ticket_num += 1
        payload = {
            "scenario": scenario,
            "signature": signature,
            "root_cause": {"signature": signature},
            "attempt": 1,
        }
        if extra:
            payload.update(extra)
        return Ticket(
            id=tid,
            run_id=run_id,
            phase="work",
            state="queued",
            resource_req=resource_req,
            priority=priority,
            attempts=0,
            payload=payload,
        )

    # 1. CPU tickets with clustering (shared signatures)
    signatures = ["sig-A", "sig-B", "sig-C"]
    for i in range(15):
        sig = rng.choice(signatures)  # Some will share signatures
        ticket = mk_ticket(resource_req="cpu", signature=sig)
        tickets.append(ticket)
        # All succeed on first attempt
        scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # 2. GPU tickets (more than typical capacity to force parking)
    for i in range(10):
        ticket = mk_ticket(resource_req="gpu", signature="sig-GPU")
        tickets.append(ticket)
        scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # 3. Driver-failed tickets (terminal, no retry)
    for i in range(3):
        ticket = mk_ticket(
            resource_req="cpu", signature="sig-DRIVER", scenario="driver_error"
        )
        tickets.append(ticket)
        scenarios[(ticket.id, 1)] = ("driver_failed", "driver_error")

    # 4. Infra-failed then succeed (retry path): fail attempt 1, ok attempt 2.
    for i in range(4):
        ticket = mk_ticket(
            resource_req="cpu", signature="sig-INFRA", scenario="infra_then_ok"
        )
        tickets.append(ticket)
        scenarios[(ticket.id, 1)] = ("infra_failed", "transport_error")
        scenarios[(ticket.id, 2)] = ("ok", "goal_met")

    # 5. needs_human via verify=False route (re-verify override). The worker
    # SUCCEEDS; the playbook's verify fails it on attempt 1 -> needs_human.
    ticket = mk_ticket(
        resource_req="cpu", signature="sig-VERIFY", extra={"needs_reverify": True}
    )
    tickets.append(ticket)
    scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # 6. needs_human via reduce flagging route. Unique signature so its cluster is
    # exactly this ticket; the playbook flags that cluster to needs_human.
    ticket = mk_ticket(
        resource_req="cpu", signature="sig-REVIEW",
        extra={"needs_reduce_review": True},
    )
    tickets.append(ticket)
    scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # 7. More cpu tickets to reach ~40 total
    remaining = 40 - len(tickets)
    for i in range(max(0, remaining)):
        sig = rng.choice(signatures)
        ticket = mk_ticket(resource_req="cpu", signature=sig)
        tickets.append(ticket)
        scenarios[(ticket.id, 1)] = ("ok", "goal_met")

    # Create MockAgent with the extended scenario table
    agent = MockAgent(healthy=True, scenarios=scenarios)

    return tickets, agent
