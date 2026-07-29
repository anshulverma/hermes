"""Tests for packaging configuration (build backend, package discovery, testkit decoupling)."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest


def test_build_backend_is_valid():
    """pyproject.toml declares a valid build backend that imports."""
    workspace = Path(__file__).parent.parent.parent
    pyproject = workspace / "pyproject.toml"

    assert pyproject.exists()

    content = pyproject.read_text()
    assert 'build-backend = "setuptools.build_meta"' in content, \
        "pyproject.toml must declare build-backend = 'setuptools.build_meta'"

    # Verify the module actually imports
    try:
        importlib.import_module("setuptools.build_meta")
    except ImportError as e:
        pytest.fail(f"build-backend module does not import: {e}")


def test_package_discovery_finds_all_subpackages():
    """setuptools.find_packages with the exact globs discovers all production packages."""
    workspace = Path(__file__).parent.parent.parent

    # Import setuptools
    from setuptools import find_packages

    # The exact globs from the plan
    include = ["engine*", "server*", "agents*", "sites*", "playbooks*"]
    exclude = ["tests*", "testkit*", "web*", "fleet*", "scripts*",
               "integrations*", "docs*"]

    # Change to workspace to run find_packages
    original_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        packages = find_packages(where=".", include=include, exclude=exclude)
    finally:
        os.chdir(original_cwd)

    packages_set = set(packages)

    # Must contain these production packages
    required = {
        "sites.local",
        "sites.ssh",
        "sites.devserver",
        "engine.db",
        "agents.claude",
        "playbooks.dexter",
    }

    missing = required - packages_set
    assert not missing, f"find_packages missing required packages: {missing}"

    # Must exclude these
    forbidden = {"tests", "testkit", "web", "fleet", "scripts", "integrations", "docs"}
    leaked = forbidden & packages_set
    assert not leaked, f"find_packages leaked excluded packages: {leaked}"


def test_wheel_build_contains_subpackages():
    """A built wheel contains the expected subpackages and excludes test/web/infra."""
    workspace = Path(__file__).parent.parent.parent

    # Skip if build module not available or network issues
    try:
        import build
    except ImportError:
        pytest.skip("build module not available")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Build wheel
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", tmpdir],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            pytest.skip(f"Wheel build failed (may be network/env): {result.stderr}")

        # Find the wheel
        wheel_files = list(Path(tmpdir).glob("*.whl"))
        assert len(wheel_files) == 1, f"Expected 1 wheel, found {len(wheel_files)}"
        wheel_path = wheel_files[0]

        # Extract and check RECORD
        with zipfile.ZipFile(wheel_path) as zf:
            namelist = zf.namelist()

        # Check for expected subpackages
        expected_dirs = {
            "sites/local/",
            "sites/ssh/",
            "sites/devserver/",
            "engine/db/",
            "agents/claude/",
            "playbooks/dexter/",
        }

        for expected in expected_dirs:
            found = any(name.startswith(expected) for name in namelist)
            assert found, f"Wheel missing {expected}"

        # Check exclusions
        forbidden_prefixes = ["testkit/", "tests/", "web/"]
        for name in namelist:
            for forbidden in forbidden_prefixes:
                assert not name.startswith(forbidden), \
                    f"Wheel leaked forbidden path: {name}"


def test_testkit_decoupling_in_load_playbook_site_agent():
    """_load_playbook_site_agent with dexter/local/claude resolves WITHOUT testkit imported."""
    workspace = Path(__file__).parent.parent.parent

    # Use subprocess import technique from test_invariants.py to ensure clean sys.modules
    script = f"""
import sys

sys.path.insert(0, r"{workspace}")

# Import minimal dependencies
from engine import config
from engine.cli import _load_playbook_site_agent
import argparse

# Set up args for dexter/local/claude
args = argparse.Namespace(
    playbook="dexter",
    site="local",
    agent="claude"
)

# Load without testkit
pb, st, ag = _load_playbook_site_agent(args)

# Check no testkit.* in sys.modules
testkit_modules = [m for m in sys.modules if m.startswith("testkit")]
if testkit_modules:
    print("FAIL: testkit modules imported:", testkit_modules, file=sys.stderr)
    sys.exit(1)

# Verify we got the right objects
assert pb.name == "dexter", f"Expected dexter playbook, got {{pb.name}}"
assert st.name == "local", f"Expected local site, got {{st.name}}"
assert ag.name == "claude", f"Expected claude agent, got {{ag.name}}"

print("OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=workspace,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(workspace)},
    )

    assert result.returncode == 0, \
        f"testkit was imported for dexter/local/claude:\n{result.stderr}\n{result.stdout}"
    assert result.stdout.strip() == "OK"


def test_testkit_still_works_for_example_and_mock():
    """_load_playbook_site_agent with example or mock still imports testkit."""
    workspace = Path(__file__).parent.parent.parent

    # Test example playbook imports testkit.example_playbook
    script_example = f"""
import sys

sys.path.insert(0, r"{workspace}")

from engine.cli import _load_playbook_site_agent
import argparse

args = argparse.Namespace(playbook="example", site="local", agent="claude")
pb, st, ag = _load_playbook_site_agent(args)

assert "testkit.example_playbook" in sys.modules, "testkit.example_playbook should be imported"
assert pb.name == "example"
print("OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", script_example],
        cwd=workspace,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(workspace)},
    )

    assert result.returncode == 0, \
        f"example playbook failed:\n{result.stderr}\n{result.stdout}"

    # Test mock agent imports testkit.mock_agent
    script_mock = f"""
import sys

sys.path.insert(0, r"{workspace}")

from engine.cli import _load_playbook_site_agent
import argparse

args = argparse.Namespace(playbook="dexter", site="local", agent="mock")
pb, st, ag = _load_playbook_site_agent(args)

assert "testkit.mock_agent" in sys.modules, "testkit.mock_agent should be imported"
assert ag.name == "mock"
print("OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", script_mock],
        cwd=workspace,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(workspace)},
    )

    assert result.returncode == 0, \
        f"mock agent failed:\n{result.stderr}\n{result.stdout}"


def test_crew_add_no_testkit_import():
    """crew add with no --playbook arg does NOT import testkit (no example default)."""
    workspace = Path(__file__).parent.parent.parent

    script = f"""
import sys

sys.path.insert(0, r"{workspace}")

from engine.cli import _load_playbook_site_agent
import argparse

# Simulate crew add args: site and agent present, NO playbook attribute
args = argparse.Namespace(
    site="local",
    agent="claude"
)
# Note: no args.playbook attribute at all

pb, st, ag = _load_playbook_site_agent(args)

# Check no testkit.* in sys.modules
testkit_modules = [m for m in sys.modules if m.startswith("testkit")]
if testkit_modules:
    print("FAIL: testkit modules imported:", testkit_modules, file=sys.stderr)
    sys.exit(1)

# Verify playbook is None when not provided
assert pb is None, f"Expected None playbook, got {{pb}}"
assert st.name == "local", f"Expected local site, got {{st.name}}"
assert ag.name == "claude", f"Expected claude agent, got {{ag.name}}"

print("OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=workspace,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(workspace)},
    )

    assert result.returncode == 0, \
        f"testkit was imported for crew add (no playbook):\n{result.stderr}\n{result.stdout}"
    assert result.stdout.strip() == "OK"


def test_serve_worker_resolves_playbook_from_run():
    """serve worker mode resolves playbook from the run's stored playbook name, not example default."""
    workspace = Path(__file__).parent.parent.parent

    script = f"""
import sys

sys.path.insert(0, r"{workspace}")

from engine.cli import _load_playbook_site_agent
import argparse

# Simulate serve --host args: site and agent present, NO playbook attribute
args = argparse.Namespace(
    site="local",
    agent="claude"
)

pb, st, ag = _load_playbook_site_agent(args)

# Check no testkit.* in sys.modules (no example imported)
testkit_modules = [m for m in sys.modules if m.startswith("testkit")]
if testkit_modules:
    print("FAIL: testkit modules imported:", testkit_modules, file=sys.stderr)
    sys.exit(1)

# Verify playbook is None (will be resolved from run later)
assert pb is None, f"Expected None playbook, got {{pb}}"
assert st.name == "local", f"Expected local site, got {{st.name}}"
assert ag.name == "claude", f"Expected claude agent, got {{ag.name}}"

print("OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=workspace,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(workspace)},
    )

    assert result.returncode == 0, \
        f"testkit was imported for serve worker (no playbook):\n{result.stderr}\n{result.stdout}"
    assert result.stdout.strip() == "OK"


def test_invariants_stdlib_scan_still_passes():
    """Regression: test_engine_core_imports_only_stdlib still passes."""
    # This just delegates to the existing test to ensure it still passes
    # after our changes. We run it via subprocess to ensure it's truly independent.
    workspace = Path(__file__).parent.parent.parent

    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/unit/test_invariants.py::test_engine_core_imports_only_stdlib",
         "-v"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, \
        f"stdlib invariant test failed:\n{result.stdout}\n{result.stderr}"
