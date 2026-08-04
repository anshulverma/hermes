"""Fan-out site adapters: one ``fan-<agent>`` site per agent.

Each fan site delegates to the built-in local site but advertises a single
``agent:<name>`` resource class, so one serve loop per agent claims only the
tickets addressed to that agent.

Importing this package registers a fan site for each built-in agent. Any other
agent registers its own the same way, with ``register_fan_site(<agent name>)``.
"""
from sites.fan.site import register_fan_site as register_fan_site

for _agent_name in ("claude", "codex"):
    register_fan_site(_agent_name)
del _agent_name
