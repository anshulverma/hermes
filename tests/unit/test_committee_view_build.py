"""The committed playbook-view bundle must match a fresh build of its source.

A view ships as a built artifact so the runtime needs no Node — only rebuilding
does. That buys a file which can drift from the .tsx it came from without anyone
noticing. This is the test that makes the drift loud.
"""
import ast
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / "playbooks" / "committee" / "view" / "dist" / "committee.umd.js"
VITE = REPO / "web" / "node_modules" / ".bin" / "vite"
REBUILD = "cd web && ./node_modules/.bin/vite build --config vite.playbook-view.config.ts"


def test_committed_view_bundle_matches_a_fresh_build():
    assert ARTIFACT.exists(), f"no committed artifact at {ARTIFACT}; build it with: {REBUILD}"

    if shutil.which("node") is None or not VITE.exists():
        pytest.skip("node / web dev dependencies unavailable; cannot rebuild the view")

    with tempfile.TemporaryDirectory() as out:
        # cwd is web/ on purpose. The entry and outDir in the config are relative
        # to the process cwd, so a build launched from the repo root cannot
        # resolve the entry at all (UNRESOLVED_ENTRY) -- it produces no build
        # rather than a different one.
        built = subprocess.run(
            [
                str(VITE), "build",
                "--config", "vite.playbook-view.config.ts",
                "--outDir", out,
                # NOT "silent": that blanks the one message that matters. With a
                # broken entry the assertion below printed "view build failed:"
                # and two empty lines.
                "--logLevel", "error",
            ],
            cwd=REPO / "web",
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert built.returncode == 0, f"view build failed:\n{built.stdout}\n{built.stderr}"

        # Exactly one file: `publicDir: false` in the config is load-bearing and
        # was otherwise unguarded -- drop it and web/public/* (favicon.svg,
        # icons.svg) lands inside the playbook package. This also pins the
        # `fileName` function, which a bare string would turn into
        # committee.umd.umd.cjs.
        assert sorted(p.name for p in Path(out).iterdir()) == ["committee.umd.js"], (
            f"the build emitted more than the bundle: "
            f"{sorted(p.name for p in Path(out).iterdir())}"
        )
        fresh = Path(out) / "committee.umd.js"
        assert fresh.read_bytes() == ARTIFACT.read_bytes(), (
            f"{ARTIFACT.relative_to(REPO)} is stale. Rebuild it with: {REBUILD}"
        )


def test_every_rule_voice_can_break_has_a_label_in_the_view_and_no_other():
    """VIOLATION_LABEL (Voice.tsx) keys == the slugs voice.violations checks,
    plus the ``retake_failed`` the playbook appends. A rule with no label shows
    its slug on screen; a label with no rule is dead."""
    voice = ast.parse((REPO / "playbooks" / "committee" / "voice.py").read_text(encoding="utf-8"))
    fn = next(n for n in voice.body if isinstance(n, ast.FunctionDef) and n.name == "violations")
    rules = {
        pair.elts[0].value
        for pair in ast.walk(fn)
        if isinstance(pair, ast.Tuple) and len(pair.elts) == 2
        and isinstance(pair.elts[0], ast.Constant) and isinstance(pair.elts[0].value, str)
    }
    tsx = (REPO / "playbooks" / "committee" / "view" / "src" / "Voice.tsx").read_text(encoding="utf-8")
    block = re.search(r"VIOLATION_LABEL[^=]*=\s*\{(.*?)\n\};", tsx, re.S)
    assert block, "no VIOLATION_LABEL object in Voice.tsx"
    labels = set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))

    assert "over_cap" in rules  # the walk found the checks at all
    assert labels == rules | {"retake_failed"}


def test_committed_view_bundle_stays_small_and_never_carries_mermaid():
    """mermaid lives on the host shelf. Bundled, it would be megabytes of
    committed, unminified artifact; the cap is what notices."""
    assert ARTIFACT.stat().st_size < 150 * 1024
    text = ARTIFACT.read_text(encoding="utf-8")
    assert "securityLevel" not in text  # mermaid's initialize() is the host's, in web/src
