# Spec: Codex agent adapter

## Goal

Add a second first-class worker-runtime agent, `codex`, alongside the reference
`claude` agent, so a run can drive OpenAI's Codex CLI as its headless worker.
Selectable via `HERMES_AGENT=codex`. Definition of done: `HERMES_AGENT=codex`
resolves a working `CodexAgent`, its unit tests pass, and the full suite stays
green.

## Background / conformance rules

- Agents conform to the `Agent` protocol **structurally** (PEP 544): no inheritance
  from the protocol class. `CodexAgent` is an independent concrete class, exactly
  as `ClaudeAgent` is.
- The result-doc contract is agent-agnostic: a worker emits a JSON result doc that
  parses to a `Result` (outcome / termination_reason / result_ref / error_summary /
  payload / evidence_ref / detail). The integrity check recomputes
  `payload_sha256` over the received payload and returns `driver_failed` /
  `contract_fail` on mismatch. An empty or unparseable doc is `driver_failed` /
  `driver_error`, and the raw output is captured into `Result.detail`.
- Modules carry a top-of-file docstring describing what the file is (project rule).
- Code must not reference doc paths / section numbers.

## Requirements

### 1. Shared result parsing (DRY, no duplication)
The result-doc parsing is identical for every CLI agent: recompute
`contracts.payload_sha256(envelope["payload"])` and, when `envelope` carries a
`payload_sha256` that differs, return `driver_failed` / `contract_fail`
(no retry); otherwise parse `raw` as the result JSON doc; an empty or unparseable
doc is `driver_failed` / `driver_error` with the raw output captured (truncated to
16384 chars) into `Result.detail`; a parsed doc's `detail`/`stack_trace` field is
surfaced into `Result.detail` (truncated).

Extract this into a shared, stdlib-only module `agents/_result_doc.py` exposing a
module-level function `parse_result_doc(raw: str, envelope: dict) -> Result` that
holds the current `ClaudeAgent.parse_result` body verbatim (including `_load_doc`
and the `_failure` construction and the `_DETAIL_LIMIT = 16384` constant), and
refactor `ClaudeAgent.parse_result` to `return parse_result_doc(raw, envelope)`.
`ClaudeAgent`'s existing behavior and every existing `test_claude_agent` test must
stay green (same outcomes, same `detail` capture). No protocol inheritance — this
is a plain module function shared by two independent concrete classes.

### 2. `CodexAgent` (`agents/codex/agent.py`)
An independent concrete class (NOT inheriting the protocol) with:
- Class attribute `name = "codex"` (the protocol's `name: str`).
- `build_invocation(envelope, driver) -> list[str]`: build the headless,
  non-interactive Codex argv. The prompt is assembled exactly as the claude agent
  does — `/goal <goal>` then, when `driver.command` is present, the methodology
  fragment `command` plus `k=v` args sorted by key (omitted when `driver` is None
  or `driver.command` is falsy). The argv is
  `["codex", "exec", prompt, "--dangerously-bypass-approvals-and-sandbox"]` — the
  non-interactive `exec` subcommand with approvals+sandbox bypassed so a headless
  worker never blocks on a prompt (the Codex analogue of claude's
  `--permission-mode bypassPermissions`). No turn cap — the transport's `timeout`
  wrapper enforces `timeout_s`. No model flag (Codex uses its configured default,
  matching the claude agent, which passes none).
- `parse_result(raw, envelope) -> Result`: `return parse_result_doc(raw, envelope)`
  (the shared helper from (1)).
- `health_checks(host, site) -> list[Check]`: return exactly two `Check`s, mirroring
  the claude agent, never invoking `codex` (no subprocess):
  - `Check("agent", ok, …)` where `ok` = `shutil.which("codex") is not None`;
    message `f"codex found at {binary}"` else `"codex not on PATH"`.
  - `Check("auth", ok, …)` where `ok` = `bool(os.environ.get("OPENAI_API_KEY"))`
    OR a Codex credentials file exists (`~/.codex/auth.json`); message
    `"openai credentials present"` else
    `"no OPENAI_API_KEY / codex credentials found"`.

### 3. Registration + discovery
- `agents/codex/__init__.py`: importing the package registers `CodexAgent` under
  the name `codex` (import side-effect), exactly like `agents/claude/__init__.py`.
- Add `import agents.codex` next to the existing `import agents.claude` in
  `engine/cli.py`'s built-in adapter imports (`_load_playbook_site_agent`) so
  `HERMES_AGENT=codex` / `--agent codex` resolves without extra config.

### 4. Tests (TDD)
Mirror `tests/unit/test_claude_agent.py` for the codex agent:
- `build_invocation` produces the expected non-interactive argv (binary + exec
  form + bypass flags), embeds the goal, includes/omits the driver methodology,
  and applies no turn cap.
- `parse_result`: maps an ok doc; a driver_failed doc; contract_fail on payload
  tamper; empty output → driver_error; unparseable output captured as `detail`;
  a worker-reported stack_trace/detail surfaced.
- `health_checks` returns exactly two `Check`s named `agent` and `auth`; the
  `agent` check's `ok` reflects whether `codex` is on PATH.
- Discovery: `HERMES_AGENT=codex` (or `engine.agent.load("codex")` after importing
  the built-ins) resolves a `CodexAgent`.
- The shared-helper refactor keeps every existing claude-agent test green.

### 5. Docs
In `docs/AUTHORING-PLAYBOOKS.md`, where the built-in agents / `HERMES_AGENT` are
described, add `codex` as a selectable built-in agent value alongside `claude`.
Code stays self-contained (no doc references in code).

## Invariants
- Structural conformance only (no protocol inheritance).
- Stdlib-only agents (json/shutil/os/time), consistent with the claude agent.
- Full suite green: `./.venv/bin/python -m pytest -m "not docker" -q`.
- No fabricated behavior; real CLI invocation shape.
