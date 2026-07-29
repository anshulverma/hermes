"""Test/demo fixtures: a temp HERMES_HOME and a canned issue file.

Stdlib-only.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

# A small canned issue set the LocalSite.issue_source can read and the
# EchoPlaybook can seed one ticket per entry from.
CANNED_ISSUES = [
    {
        "id": "BUG-1",
        "title": "Null pointer in parser",
        "ref": "file:///issues/BUG-1",
        "data": {"severity": "high", "cluster": "parser"},
    },
    {
        "id": "BUG-2",
        "title": "Race in scheduler",
        "ref": "file:///issues/BUG-2",
        "data": {"severity": "medium", "cluster": "scheduler"},
    },
    {
        "id": "BUG-3",
        "title": "Leak in parser",
        "ref": "file:///issues/BUG-3",
        "data": {"severity": "low", "cluster": "parser"},
    },
]


def write_canned_issues(path, issues=None) -> Path:
    """Write the canned issues to `path` as JSON and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(issues if issues is not None else CANNED_ISSUES))
    return path


@contextmanager
def temp_hermes_home():
    """Context manager: a temp dir set as HERMES_HOME (restored on exit).

    Yields the Path to the temp HERMES_HOME.
    """
    prev = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory(prefix="hermes-home-") as d:
        os.environ["HERMES_HOME"] = d
        try:
            yield Path(d)
        finally:
            if prev is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = prev
