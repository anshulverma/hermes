"""Static validation: constraints.txt exists, pins >=floors, Dockerfile wired."""
import re
from pathlib import Path


def test_constraints_file_exists():
    """constraints.txt must exist at repo root."""
    repo = Path(__file__).parent.parent.parent
    assert (repo / "constraints.txt").exists()


def test_constraints_pins_key_packages():
    """constraints.txt must pin (with ==) at least fastapi/uvicorn/starlette/httpx."""
    repo = Path(__file__).parent.parent.parent
    constraints = (repo / "constraints.txt").read_text()

    required = {"fastapi", "uvicorn", "starlette", "httpx"}
    found = set()

    for line in constraints.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Match package==version
        match = re.match(r"^([a-zA-Z0-9_-]+)==", line)
        if match:
            pkg = match.group(1).lower()
            if pkg in required:
                found.add(pkg)

    assert found == required, f"Missing pins: {required - found}"


def test_constraints_versions_satisfy_floors():
    """Every constraint version must be >= its pyproject floor."""
    repo = Path(__file__).parent.parent.parent

    # Parse constraints.txt
    constraints_text = (repo / "constraints.txt").read_text()
    constraints = {}
    for line in constraints_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_-]+)==(.+)$", line)
        if match:
            pkg, version = match.groups()
            constraints[pkg.lower()] = version.strip()

    # Parse pyproject.toml server extra floors
    pyproject = (repo / "pyproject.toml").read_text()
    floors = {}
    in_server = False
    for line in pyproject.splitlines():
        if line.strip() == 'server = [':
            in_server = True
            continue
        if in_server:
            # Match "package>=version" (possibly with extras like [standard])
            # Strip the extras from package name: uvicorn[standard] -> uvicorn
            match = re.search(r'"([a-zA-Z0-9_-]+)(?:\[.+?\])?>=([^"]+)"', line)
            if match:
                pkg, floor = match.groups()
                floors[pkg.lower()] = floor.strip()
            if ']' in line:
                break

    # Also get httpx floor from dev extra (it's a test dep)
    in_dev = False
    for line in pyproject.splitlines():
        if line.strip() == 'dev = [':
            in_dev = True
            continue
        if in_dev:
            match = re.search(r'"([a-zA-Z0-9_-]+)(?:\[.+?\])?>=([^"]+)"', line)
            if match:
                pkg, floor = match.groups()
                if pkg.lower() == "httpx":
                    floors[pkg.lower()] = floor.strip()
            if ']' in line:
                break

    # Verify each constraint >= floor
    from packaging.version import parse as parse_version

    for pkg in ["fastapi", "uvicorn", "httpx"]:
        assert pkg in constraints, f"Missing constraint for {pkg}"
        assert pkg in floors, f"Missing floor for {pkg}"

        constraint_ver = parse_version(constraints[pkg])
        floor_ver = parse_version(floors[pkg])

        assert constraint_ver >= floor_ver, \
            f"{pkg}: constraint {constraints[pkg]} < floor {floors[pkg]}"

    # starlette is an implicit dep, no floor in pyproject, but must be pinned
    assert "starlette" in constraints, "Missing starlette pin"


def test_dockerfile_references_constraints():
    """Dockerfile.control-plane must reference constraints.txt in pip install."""
    repo = Path(__file__).parent.parent.parent
    dockerfile = (repo / "fleet" / "Dockerfile.control-plane").read_text()

    # Must contain "-c constraints.txt" in the pip install line
    assert "-c constraints.txt" in dockerfile, \
        "Dockerfile must use '-c constraints.txt' in pip install"
    assert "pip install" in dockerfile and ".[server]" in dockerfile, \
        "Dockerfile must install .[server] extra"
