"""Testkit: a mock agent + example playbook + fixtures for tests/demos.

Importing this package registers the `example` playbook and the `mock` agent.
"""
from testkit import example_playbook as example_playbook  # noqa: F401 (registers "example")
from testkit import mock_agent as mock_agent  # noqa: F401 (registers "mock")
