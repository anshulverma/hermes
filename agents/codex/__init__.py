"""The OpenAI Codex agent adapter.

Importing this package registers CodexAgent under the name "codex".
"""
from agents.codex import agent as agent  # noqa: F401  (import side-effect: registers "codex")
