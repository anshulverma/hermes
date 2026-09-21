"""The committed playbook-view bundle must match a fresh build of its source.

A view ships as a built artifact so the runtime needs no Node — only rebuilding
does. That buys a file which can drift from the .tsx it came from without anyone
noticing. This is the test that makes the drift loud.
"""
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
        # cwd is web/ on purpose: the emitted //#region comment names the entry
        # relative to the cwd, so building from elsewhere changes the bytes.
        built = subprocess.run(
            [
                str(VITE), "build",
                "--config", "vite.playbook-view.config.ts",
                "--outDir", out,
                "--logLevel", "silent",
            ],
            cwd=REPO / "web",
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert built.returncode == 0, f"view build failed:\n{built.stdout}\n{built.stderr}"

        fresh = Path(out) / "committee.umd.js"
        assert fresh.exists(), (
            f"build emitted no committee.umd.js, only "
            f"{sorted(p.name for p in Path(out).iterdir())}"
        )
        assert fresh.read_bytes() == ARTIFACT.read_bytes(), (
            f"{ARTIFACT.relative_to(REPO)} is stale. Rebuild it with: {REBUILD}"
        )
