"""CodexAgent — OpenAI Codex CLI adapter.

Renders a Driver + GoalEnvelope into a headless ``codex exec`` invocation and
parses the worker's native ``--json`` JSONL output + ``-o`` answer file back
into a ``Result``. There is no turn cap: the wall-clock budget is enforced by
the transport's ``timeout`` wrapper over ``envelope["timeout_s"]``.

The answer is authoritative from the ``-o`` file (plain text written by codex);
the JSONL stdout carries the transport-level success signal (``turn.completed``)
and usage. Non-JSON preamble lines in stdout are skipped.

Selected via ``HERMES_AGENT=codex``. Stdlib-only (json, os, re, shutil,
tempfile, time).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
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

# Per-ticket answer files live under a hermes-owned sub-dir in tmp.
_WORK_SUBDIR = "hermes-codex"

# Characters unsafe in a single filename component are folded into "-".
_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


class CodexAgent:
    """OpenAI Codex agent adapter: ``codex exec … --json -o <file>``."""

    name = "codex"

    # --- invocation -----------------------------------------------------

    def build_invocation(self, envelope: dict, driver: Driver) -> list[str]:
        """Build the headless ``codex`` argv.

        Prompt = ``/goal <goal>`` plus the methodology ``driver.command`` (with
        its args) when present, omitted when null. ``--json`` enables JSONL
        output; ``-o <path>`` writes the final answer to a per-ticket file so
        it is not mixed into the JSONL event stream. Any stale answer file from
        a prior attempt is removed before the run. No ``--max-turns``: the
        transport's ``timeout`` wrapper enforces ``timeout_s``.
        """
        goal = envelope["goal_envelope"]["goal"]
        prompt = self._build_prompt(goal, driver)
        out_path = self._out_path(envelope)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        if os.path.exists(out_path):
            os.remove(out_path)
        return [
            "codex", "exec", prompt,
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-o", out_path,
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

    @staticmethod
    def _out_path(envelope: dict) -> str:
        """The answer file path for this ticket, stable across build/parse calls."""
        safe = (
            _UNSAFE_IN_FILENAME.sub("-", envelope.get("ticket_id", "ticket")) or "ticket"
        )
        work_dir = os.path.join(tempfile.gettempdir(), _WORK_SUBDIR)
        return os.path.join(work_dir, f"{safe}.out.txt")

    # --- result parsing -------------------------------------------------

    def parse_result(self, raw: str, envelope: dict) -> Result:
        """Parse the codex JSONL stdout + answer file into a Result.

        1. Payload integrity check: recompute payload_sha256; mismatch →
           driver_failed / contract_fail (no retry).
        2. Parse JSONL events from stdout (non-JSON preamble lines are skipped).
           ``turn.completed`` = transport-level success; any ``turn.failed`` or
           ``error`` event, or the absence of ``turn.completed``, is a failure.
        3. Read the authoritative answer from the ``-o`` file.
        4. If the answer text itself parses as a hermes result doc (has an
           ``outcome`` key), delegate to the shared parse_result_doc path.
        5. Otherwise wrap as ok / goal_met with payload={"answer": text},
           preserving the thread_id as result_ref.
        The answer file is removed after parsing. Never raises: any unexpected
        structure returns an honest failure Result.
        """
        now = time.time()
        out_path = self._out_path(envelope)
        detail = (raw or "")[:_DETAIL_LIMIT] or None

        expected = envelope.get("payload_sha256")
        actual = contracts.payload_sha256(envelope.get("payload") or {})
        if expected is not None and expected != actual:
            return self._failure(
                f"payload_sha256 mismatch: expected {expected}, got {actual}",
                now,
            )

        try:
            result = self._do_parse(raw, out_path, envelope, now, detail)
        except Exception as exc:  # safety net — transport does not catch exceptions
            result = self._failure(
                f"unexpected parse error: {exc}", now, detail=detail
            )

        try:
            os.remove(out_path)
        except OSError:
            pass
        return result

    def _do_parse(
        self,
        raw: str,
        out_path: str,
        envelope: dict,
        now: float,
        detail: str | None,
    ) -> Result:
        """Inner parse — called from parse_result to suppress all exceptions."""
        events = self._parse_jsonl(raw)

        thread_id = None
        usage = None
        completed = False
        fail_reason = None

        for event in events:
            t = event.get("type")
            if t == "thread.started":
                thread_id = event.get("thread_id")
            elif t == "turn.completed":
                completed = True
                usage = event.get("usage")
            elif t in ("turn.failed", "error"):
                fail_reason = event.get("message") or event.get("error") or t

        if not completed or fail_reason is not None:
            summary = (
                fail_reason
                if fail_reason
                else "codex run did not complete (no turn.completed event)"
            )
            return self._failure(summary, now, detail=detail)

        if not os.path.exists(out_path):
            return self._failure(
                f"codex wrote no answer file at {out_path}", now, detail=detail
            )

        try:
            with open(out_path, encoding="utf-8") as fh:
                answer = fh.read()
        except OSError as exc:
            return self._failure(
                f"could not read codex answer file: {exc}", now, detail=detail
            )

        if not isinstance(answer, str) or not answer.strip():
            return self._failure(
                "codex answer file is empty", now, detail=detail
            )

        answer = answer.strip()

        # If the answer is itself a hermes result doc, honour the structured path.
        try:
            inner = json.loads(answer)
            if isinstance(inner, dict) and "outcome" in inner:
                return parse_result_doc(answer, envelope)
        except (json.JSONDecodeError, TypeError):
            pass

        result_ref = f"codex:thread:{thread_id}" if thread_id else None

        return Result(
            outcome="ok",
            termination_reason="goal_met",
            result_ref=result_ref,
            error_summary=None,
            started_at=now,
            ended_at=now,
            payload={"answer": answer},
            evidence_ref=out_path,
        )

    @staticmethod
    def _parse_jsonl(raw: str) -> list[dict]:
        """Parse JSONL from stdout, skipping non-JSON preamble lines."""
        events: list[dict] = []
        for line in (raw or "").splitlines():
            stripped = line.strip()
            if not stripped.startswith("{"):
                continue
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    events.append(obj)
            except (json.JSONDecodeError, TypeError):
                pass
        return events

    @staticmethod
    def _failure(
        summary: str,
        now: float,
        detail: str | None = None,
    ) -> Result:
        return Result(
            outcome="driver_failed",
            termination_reason="driver_error",
            result_ref=None,
            error_summary=(summary or "")[:_DETAIL_LIMIT] or None,
            started_at=now,
            ended_at=now,
            payload={},
            evidence_ref=None,
            detail=detail,
        )

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
