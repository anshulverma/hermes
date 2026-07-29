"""The reference `claude` agent adapter.

Importing this package registers ClaudeAgent under the name "claude".
"""
from agents.claude import agent as agent  # noqa: F401  (import side-effect: registers "claude")
