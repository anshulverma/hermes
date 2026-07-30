# Hermes `codex` agent adapter — implementation plan

Status: **draft**. Spec: `docs/specs/codex-agent.md` (hardened to convergence).
Depends on: engine-core (`engine/agent.py` `Agent` protocol, `engine/models.py`
`Result`/`Check`, `engine/contracts.py` `payload_sha256`) — **already built** — and
the reference `agents/claude/agent.py`, which this mirrors.

Vertical slices in dependency order. Each is independently testable, follows **TDD**
(write the failing test first, watch it fail, minimal code to green, refactor), and
ends GREEN before the next begins. Each lists **scope**, **files**, the **failing
tests to write first**, and its **DoD**.

Runner: `./.venv/bin/python -m pytest -m "not docker" -q`. Commit after each slice.

---

## Global constraints (apply to every slice)

- **Stdlib-only agents.** `agents/*` import only stdlib (`json`, `shutil`, `os`,
  `time`) — mirror `agents/claude/agent.py`. No third-party runtime imports.
- **Structural conformance (PEP 544).** `CodexAgent` does NOT inherit from the
  `Agent` protocol; it is an independent concrete class that structurally satisfies
  it (attribute `name: str`; methods `build_invocation`, `parse_result`,
  `health_checks` with the exact signatures in `engine/agent.py`). The shared
  parser is a plain module function, not a base class.
- **Match the real interfaces.** `build_invocation(self, envelope: dict, driver: Driver) -> list[str]`,
  `parse_result(self, raw: str, envelope: dict) -> Result`,
  `health_checks(self, host: str, site: "Site") -> list[Check]`. `Result` and
  `Check` come from `engine.models`; the integrity hash from
  `engine.contracts.payload_sha256`.
- **No behavior change to the claude agent.** The Slice 1 refactor must keep every
  existing `tests/unit/test_claude_agent.py` test green with no edits to those tests.
- **Module docstrings.** Every new module opens with a concise top-of-file docstring
  describing what the file is.
- **Code self-contained — no doc references in code.** No `§N`, no `Slice N`, no
  `docs/…` / `*-plan.md` paths, no "per the spec/plan" in comments, docstrings, or
  strings. Code-to-code references (module/function names) are fine.
- **Never fake test data or assertions.** Drive real parsing against real envelopes;
  the only doubles are honest (e.g. monkeypatching `shutil.which` for health tests).

---

## Slice 1 — Shared result-doc parser + claude refactor

**Scope.** Extract the agent-agnostic result-doc parsing into a shared module and
make `ClaudeAgent` delegate to it, unchanged in behavior.

**Files.**
- `agents/_result_doc.py` (new): module docstring; `_DETAIL_LIMIT = 16384`;
  `parse_result_doc(raw: str, envelope: dict) -> Result` holding the current
  `ClaudeAgent.parse_result` logic verbatim — the `payload_sha256` integrity check
  (via `engine.contracts`) returning `driver_failed`/`contract_fail` on mismatch;
  `_load_doc(raw)` (empty/non-dict/JSON-error → None); on `None` a
  `driver_failed`/`driver_error` `Result` with `detail=(raw or "")[:_DETAIL_LIMIT] or None`;
  otherwise a `Result` built from the doc with `detail = doc.get("detail") or
  doc.get("stack_trace")` truncated. Keep `_load_doc` and the failure builder as
  module-level helpers here.
- `agents/claude/agent.py` (edit): `parse_result` becomes
  `return parse_result_doc(raw, envelope)`; remove the now-moved `_load_doc`/
  `_failure`/`_DETAIL_LIMIT` from the class (or leave `build_invocation`/`health`
  untouched). Keep the class's public behavior identical.

**Tests to write first** (`tests/unit/test_result_doc.py`, new):
- `parse_result_doc` on a valid ok doc → `outcome=="ok"`, fields mapped.
- on a `driver_failed` doc → outcome/termination_reason/error_summary mapped.
- on payload tamper (envelope `payload_sha256` set to a wrong value) →
  `driver_failed`/`contract_fail`.
- on `""` → `driver_failed`/`driver_error`, `detail is None`.
- on unparseable non-empty raw (e.g. `"not json"`) → `driver_error`,
  `detail == "not json"`.
- on a doc carrying `stack_trace` → `Result.detail` equals it.

**DoD.** New `test_result_doc.py` passes; **all existing `test_claude_agent.py`
tests pass unchanged**; full suite green.

---

## Slice 2 — `CodexAgent`

**Scope.** The concrete codex agent, mirroring `ClaudeAgent` but for the Codex CLI.

**Files.**
- `agents/codex/agent.py` (new): module docstring; `class CodexAgent` with
  `name = "codex"`; `build_invocation` returning
  `["codex", "exec", prompt, "--dangerously-bypass-approvals-and-sandbox"]` where
  `prompt` is assembled exactly as claude does (`/goal <goal>`, then the methodology
  fragment `driver.command` + `k=v` args sorted by key when `driver.command` is
  truthy); `parse_result` = `return parse_result_doc(raw, envelope)` (from Slice 1);
  `health_checks` returning `[Check("agent", …), Check("auth", …)]` per the spec
  (codex-on-PATH via `shutil.which`; `OPENAI_API_KEY` env or `~/.codex/auth.json`).
  Register at import time: `engine.agent.register("codex", CodexAgent())`.
- `agents/codex/__init__.py` (new): docstring; `from agents.codex import agent as agent`
  (import side-effect registers "codex"), mirroring `agents/claude/__init__.py`.

**Tests to write first** (`tests/unit/test_codex_agent.py`, new — mirror
`test_claude_agent.py`):
- `build_invocation` → `["codex", "exec", <prompt>, "--dangerously-bypass-approvals-and-sandbox"]`;
  prompt starts `/goal <goal>`; includes the methodology fragment with sorted
  `k=v` args when `driver.command` set; omits it when `driver.command` is None; no
  `--max-turns`/turn cap token present.
- `parse_result` delegates: ok doc → ok; empty → driver_error; unparseable →
  `detail` captured (proves the shared helper is wired).
- `health_checks` → two `Check`s named `agent`, `auth`; with `shutil.which`
  monkeypatched to return a path, `agent` check `ok is True`; monkeypatched to
  `None`, `ok is False`.

**DoD.** `test_codex_agent.py` passes; full suite green. (Discovery via
`HERMES_AGENT` is Slice 3.)

---

## Slice 3 — Registration/discovery wiring + docs

**Scope.** Make `HERMES_AGENT=codex` resolve without extra config, and document it.

**Files.**
- `engine/cli.py` (edit): in `_import_registration_modules`, add
  `import agents.codex` next to `import agents.claude`.
- `docs/AUTHORING-PLAYBOOKS.md` (edit): where built-in agents / `HERMES_AGENT` are
  described, list `codex` alongside `claude`.

**Tests to write first** (add to `tests/unit/test_discovery.py`):
- `test_codex_agent_resolves_via_builtin_registration`: call
  `engine.cli._import_registration_modules()`, then `engine.agent.load("codex")`
  returns an object with `name == "codex"` and `isinstance(obj, engine.agent.Agent)`
  (the `@runtime_checkable` protocol). This proves the Slice-3 `import agents.codex`
  line wired discovery without extra env config.

**DoD.** Discovery test passes; full suite green; `docs/AUTHORING-PLAYBOOKS.md`
lists `codex`.

---

## Acceptance

- `./.venv/bin/python -m pytest -m "not docker" -q` green.
- `HERMES_AGENT=codex` resolves a working `CodexAgent` (Slice 3 test).
- Claude agent behavior unchanged (Slice 1 DoD).
