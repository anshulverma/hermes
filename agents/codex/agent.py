"""CodexAgent — OpenAI Codex CLI adapter.

Renders a Driver + GoalEnvelope into a headless ``codex exec`` invocation and
parses the worker's emitted result doc / stdout back into a ``Result``. There is
no turn cap (no ``--max-turns``): the wall-clock budget is enforced by the
transport's ``timeout`` wrapper over ``envelope["timeout_s"]``.

Integrity: on parse, the agent RECOMPUTES ``payload_sha256`` over the received
payload and, on mismatch, returns ``driver_failed`` / ``contract_fail`` with
no retry.

Selected via ``HERMES_AGENT=codex``. Stdlib-only (os, shutil).
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


class CodexAgent:
    """OpenAI Codex agent adapter: ``codex exec``."""

    name = "codex"

    # --- invocation -----------------------------------------------------

    def build_invocation(self, envelope: dict, driver: Driver) -> list[str]:
        """Build the headless ``codex`` argv.

        Prompt = ``/goal <goal>`` plus the methodology ``driver.command`` (with
        its args) when present, omitted when null. No ``--max-turns``: the
        transport's ``timeout`` wrapper enforces ``timeout_s``.
        """
        goal = envelope["goal_envelope"]["goal"]
        prompt = self._build_prompt(goal, driver)
        return ["codex", "exec", prompt, "--dangerously-bypass-approvals-and-sandbox"]

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

        ``agent`` = the ``codex`` binary is on PATH; ``auth`` = an OpenAI
        credential is present (``OPENAI_API_KEY`` env or a ``~/.codex/auth.json``
        credentials file). Never invokes ``codex`` (no subprocess), so it is
        cheap and side-effect-free.
        """
        binary = shutil.which("codex")
        agent_ok = binary is not None
        agent_check = Check(
            "agent",
            agent_ok,
            f"codex found at {binary}" if agent_ok else "codex not on PATH",
        )

        auth_ok = bool(os.environ.get("OPENAI_API_KEY")) or self._has_credentials()
        auth_check = Check(
            "auth",
            auth_ok,
            "openai credentials present" if auth_ok
            else "no OPENAI_API_KEY / codex credentials found",
        )
        return [agent_check, auth_check]

    @staticmethod
    def _has_credentials() -> bool:
        home = os.path.expanduser("~")
        auth_json = os.path.join(home, ".codex/auth.json")
        return os.path.exists(auth_json)


# --- registration (import side-effect) -----------------------------------

_agent.register("codex", CodexAgent())
