#!/usr/bin/env bash
# Run all tests for Hermes engine core.
#
# Usage: scripts/run_tests.sh [pytest args...]

set -euo pipefail

# Resolve venv relative to this script's parent (the repo root)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTEST="${REPO_ROOT}/.venv/bin/python"

# Check if venv/pytest exists
if [[ ! -x "$PYTEST" ]]; then
    echo "ERROR: Virtual environment not found at ${REPO_ROOT}/.venv" >&2
    echo "Create it with:" >&2
    echo "  cd ${REPO_ROOT}" >&2
    echo "  python3 -m venv .venv" >&2
    echo "  .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
fi

# Run pytest through the repo's venv
exec "$PYTEST" -m pytest "$@"
