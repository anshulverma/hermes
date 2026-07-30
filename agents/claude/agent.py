"""ClaudeAgent — the reference agent adapter.

Renders a Driver + GoalEnvelope into a headless ``claude -p`` invocation and
parses the worker's emitted result doc / stdout back into a ``Result``. There is
no turn cap (no ``--max-turns``): the wall-clock budget is enforced by the
transport's ``timeout`` wrapper over ``envelope["timeout_s"]``.

Integrity: on parse, the agent RECOMPUTES ``payload_sha256`` over the received
payload and, on mismatch, returns ``driver_failed`` / ``contract_fail`` with
no retry.

Selected via ``HERMES_AGENT=claude`` (the default). Stdlib-only (json, shutil,
os, time).
"""
from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from agents._result_doc import parse_result_doc
from engine import agent as _agent
from engine.models import Check, Driver, Result

if TYPE_CHECKING:  # avoid import cycle
    from engine.site import Site


class ClaudeAgent:
    """Claude Code agent adapter: ``claude -p "/goal …"``."""

    name = "claude"

    # --- invocation -----------------------------------------------------

    def build_invocation(self, envelope: dict, driver: Driver) -> list[str]:
        """Build the headless ``claude`` argv.

        Prompt = ``/goal <goal>`` plus the methodology ``driver.command`` (with
        its args) when present, omitted when null. No ``--max-turns``: the
        transport's ``timeout`` wrapper enforces ``timeout_s``.
        """
        goal = envelope["goal_envelope"]["goal"]
        prompt = self._build_prompt(goal, driver)
        return ["claude", "-p", prompt, "--permission-mode", "bypassPermissions"]

    @staticmethod
    def _build_prompt(goal: str, driver: Driver) -> str:
        """Assemble the prompt: the goal, then the methodology command + args."""
        parts = [f"/goal {goal}"]
        if driver is not None and driver.command:
            fragment = driver.command
            args = driver.args or {}
            if args:
                rendered = " ".join(f"{k}={args[k]}" for k in sorted(args))
                fragment = f"{fragment} {rendered}"
            parts.append(fragment)
        return " ".join(parts)

    # --- result parsing -------------------------------------------------

    def parse_result(self, raw: str, envelope: dict) -> Result:
        """Map the worker's emitted result doc / stdout to a ``Result``.

        Integrity check first: recompute ``payload_sha256`` over the received
        payload and, on mismatch, return ``driver_failed`` / ``contract_fail``
        (no retry). Otherwise parse ``raw`` as the result JSON doc; an empty or
        unparseable doc is a ``driver_failed`` / ``driver_error``.
        """
        return parse_result_doc(raw, envelope)

    # --- health ---------------------------------------------------------

    def health_checks(self, host: str, site: "Site") -> list[Check]:
        """Return the agent_ok + auth_ok checks.

        ``agent`` = the ``claude`` binary is on PATH; ``auth`` = an Anthropic
        credential is present (``ANTHROPIC_API_KEY`` env or a ``~/.claude``
        credentials file). Never invokes ``claude`` (no subprocess), so it is
        cheap and side-effect-free.
        """
        binary = shutil.which("claude")
        agent_ok = binary is not None
        agent_check = Check(
            "agent",
            agent_ok,
            f"claude found at {binary}" if agent_ok else "claude not on PATH",
        )

        auth_ok = bool(os.environ.get("ANTHROPIC_API_KEY")) or self._has_credentials()
        auth_check = Check(
            "auth",
            auth_ok,
            "anthropic credentials present" if auth_ok
            else "no ANTHROPIC_API_KEY / claude credentials found",
        )
        return [agent_check, auth_check]

    @staticmethod
    def _has_credentials() -> bool:
        home = os.path.expanduser("~")
        for candidate in (".claude.json", ".claude/.credentials.json"):
            if os.path.exists(os.path.join(home, candidate)):
                return True
        return False


# --- registration (import side-effect) -----------------------------------

_agent.register("claude", ClaudeAgent())
