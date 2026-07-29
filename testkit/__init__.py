"""Test doubles and demo fixtures. Registers the mock agent and example playbook for integration testing without real Claude or SSH."""
from testkit import example_playbook as example_playbook  # noqa: F401 (registers "example")
from testkit import mock_agent as mock_agent  # noqa: F401 (registers "mock")
