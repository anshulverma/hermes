#!/usr/bin/env bash
# Run all tests for Hermes engine core.
#
# Usage: scripts/run_tests.sh [pytest args...]

set -euo pipefail

# Resolve venv relative to this script's parent (the repo root)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTEST="${REPO_ROOT}/.venv/bin/python"

# Run pytest through the repo's venv
exec "$PYTEST" -m pytest "$@"
