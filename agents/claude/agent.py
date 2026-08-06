"""ClaudeAgent — the reference agent adapter.

Renders a Driver + GoalEnvelope into a headless ``claude -p`` invocation and
parses the worker's native ``--output-format json`` envelope back into a
``Result``. There is no turn cap (no ``--max-turns``): the wall-clock budget is
enforced by the transport's ``timeout`` wrapper over ``envelope["timeout_s"]``.

Selected via ``HERMES_AGENT=claude`` (the default). Stdlib-only (json, os,
shutil, time).
"""
from __future__ import annotations

import json
import os
import shutil
import time
from typing import TYPE_CHECKING

from agents._result_doc import parse_result_doc
from engine import agent as _agent
from engine import contracts
from engine.models import Check, Driver, Result

if TYPE_CHECKING:  # avoid import cycle
    from engine.site import Site

# Cap captured failure detail so a runaway worker can't bloat the db.
_DETAIL_LIMIT = 16384


class ClaudeAgent:
    """Claude Code agent adapter: ``claude -p "/goal …" --output-format json``."""

    name = "claude"

    # --- invocation -----------------------------------------------------

    def build_invocation(self, envelope: dict, driver: Driver) -> list[str]:
        """Build the headless ``claude`` argv.

        Prompt = ``/goal <goal>`` plus the methodology ``driver.command`` (with
        its args) when present, omitted when null. ``--output-format json``
        makes claude emit a structured JSON envelope on stdout rather than prose.
        No ``--max-turns``: the transport's ``timeout`` wrapper enforces
        ``timeout_s``.
        """
        goal = envelope["goal_envelope"]["goal"]
        prompt = self._build_prompt(goal, driver)
        return [
            "claude", "-p", prompt,
            "--permission-mode", "bypassPermissions",
            "--output-format", "json",
        ]

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
        """Parse the native ``--output-format json`` claude envelope into a Result.

        1. Payload integrity check: recompute payload_sha256; mismatch →
           driver_failed / contract_fail (no retry).
        2. Locate the JSON envelope in stdout by scanning for the last line that
           parses as a JSON dict (skips preamble banner lines).
        3. ``is_error`` true → driver_failed / driver_error with raw in detail.
        4. Extract the answer from the ``result`` field.
        5. If the answer text itself parses as a hermes result doc (has an
           ``outcome`` key), delegate to the shared parse_result_doc path so a
           playbook that instructs the agent to emit a structured result still
           gets one.
        6. Otherwise wrap as ok / goal_met with payload={"answer": text},
           preserving session identity and deriving started_at from duration_ms.
        Never raises: any unexpected structure returns an honest failure Result.
        """
        now = time.time()

        expected = envelope.get("payload_sha256")
        actual = contracts.payload_sha256(envelope.get("payload") or {})
        if expected is not None and expected != actual:
            return self._failure(
                "contract_fail",
                f"payload_sha256 mismatch: expected {expected}, got {actual}",
                now,
            )

        try:
            return self._do_parse(raw, envelope, now)
        except Exception as exc:  # safety net — transport does not catch exceptions
            return self._failure(
                "driver_error",
                f"unexpected parse error: {exc}",
                now,
                detail=(raw or "")[:_DETAIL_LIMIT] or None,
            )

    def _do_parse(self, raw: str, envelope: dict, now: float) -> Result:
        """Inner parse — called from parse_result to suppress all exceptions."""
        doc = self._extract_json_envelope(raw)
        if doc is None:
            return self._failure(
                "driver_error",
                "no parseable JSON envelope in claude stdout",
                now,
                detail=(raw or "")[:_DETAIL_LIMIT] or None,
            )

        is_error = doc.get("is_error", False)
        if is_error:
            api_err = doc.get("api_error_status")
            summary = (
                f"claude reported is_error (api_error_status={api_err})"
                if api_err else "claude reported is_error"
            )
            return self._failure(
                "driver_error", summary, now,
                detail=(raw or "")[:_DETAIL_LIMIT] or None,
            )

        # A prompt claude refused to run (an over-long /goal, an unknown command)
        # comes back as is_error:false / subtype:"success" carrying the rejection
        # text in ``result`` — but with num_turns 0, because the model never ran.
        # Zero turns is therefore never an answer, whatever ``result`` says; taking
        # it at face value banks a CLI message as the worker's finding.
        turns = doc.get("num_turns")
        if isinstance(turns, int) and turns <= 0:
            return self._failure(
                "driver_error",
                "claude returned 0 turns: the prompt was rejected before the "
                "model ran",
                now,
                detail=(raw or "")[:_DETAIL_LIMIT] or None,
            )

        answer = doc.get("result")
        if not isinstance(answer, str) or not answer.strip():
            return self._failure(
                "driver_error",
                "claude envelope carries no result text",
                now,
                detail=(raw or "")[:_DETAIL_LIMIT] or None,
            )

        # If the answer is itself a hermes result doc, honour the structured path.
        try:
            inner = json.loads(answer)
            if isinstance(inner, dict) and "outcome" in inner:
                return parse_result_doc(answer, envelope)
        except (json.JSONDecodeError, TypeError):
            pass

        # Derive started_at from the reported duration so attempt durations are not zero.
        duration_ms = doc.get("duration_ms")
        started_at = (
            now - duration_ms / 1000.0
            if isinstance(duration_ms, (int, float)) else now
        )

        # Preserve session identity as result_ref.
        session_id = doc.get("session_id")
        uuid = doc.get("uuid")
        if session_id:
            result_ref = f"claude:session:{session_id}"
        elif uuid:
            result_ref = f"claude:uuid:{uuid}"
        else:
            result_ref = None

        return Result(
            outcome="ok",
            termination_reason="goal_met",
            result_ref=result_ref,
            error_summary=None,
            started_at=started_at,
            ended_at=now,
            payload={"answer": answer},
            evidence_ref=None,
        )

    @staticmethod
    def _extract_json_envelope(raw: str) -> dict | None:
        """Scan stdout lines; return the last that parses as a JSON dict.

        Claude emits preamble banner lines before the JSON result object, so we
        skip any line that does not start with ``{`` or does not parse as a
        dict.
        """
        if not raw or not raw.strip():
            return None
        last = None
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped.startswith("{"):
                continue
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    last = obj
            except (json.JSONDecodeError, TypeError):
                pass
        return last

    @staticmethod
    def _failure(
        termination_reason: str,
        summary: str,
        now: float,
        detail: str | None = None,
    ) -> Result:
        return Result(
            outcome="driver_failed",
            termination_reason=termination_reason,
            result_ref=None,
            error_summary=summary,
            started_at=now,
            ended_at=now,
            payload={},
            evidence_ref=None,
            detail=detail,
        )

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
