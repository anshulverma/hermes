"""testkit.scenarios — deterministic fake scenarios for integration testing.

Scenarios are pre-built collections of tickets + MockAgent result tables that
exercise specific engine paths (clustering, retry, parking, needs_human routes).
"""
from testkit.scenarios.fleet import build_fleet_scenario  # noqa: F401
