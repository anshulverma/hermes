"""The committee's transcript, and the one file a worker may edit.

``thread.md`` is the whole channel: it is what every worker reads before it
speaks and what a human reads afterwards. It is append-only -- opened ``"a"``,
flushed per call, no temp file and no locking -- because the master writes it
from one process, one settled turn at a time. A turn that produced no finding
still gets an entry (``NO_TURN``), so the transcript stays contiguous and the
loss is visible rather than silently missing.

The other half of the run directory is ``revised/``: a byte copy of the
artifact, made once, that the junior IC edits when the owner delegates. The
original is never touched, and ``digest`` is what lets ``reduce`` tell whether
the edit actually landed.

Stdlib-only.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from engine import config as _config

from playbooks.committee import cast

# The body written for a turn whose worker produced no finding.
NO_TURN = "_(no turn delivered — the worker failed; see hermes show)_"


def path(run_id: str) -> Path:
    """Absolute path to the run's transcript. Creates the run directory."""
    return _config.state_dir("runs", run_id) / "thread.md"


def _append(run_id: str, text: str) -> None:
    """Append ``text`` to the transcript and flush it."""
    with open(path(run_id), "a", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()


def _entry(run_id: str, heading: str, body: str) -> None:
    """Append one ``## ...`` entry, substituting NO_TURN for an empty body."""
    text = body.strip() if isinstance(body, str) else ""
    _append(run_id, f"\n{heading}\n\n{text or NO_TURN}\n")


def write_header(run_id: str, *, charge: str, artifact: str, roster: list[str]) -> None:
    """Open the transcript with the charge, the artifact path and the roster."""
    lines = [
        f"# Committee — {run_id}",
        "",
        f"**Charge:** {charge}",
        "",
        f"**Artifact:** {artifact}",
        "",
        "**Committee:**",
        "",
    ]
    lines.extend(f"- {member}" for member in roster)
    _append(run_id, "\n".join(lines) + "\n")


def append_turn(run_id: str, *, turn: int, role: str, body: str) -> None:
    """Append one speaker's turn under ``## turn NN — Name, Title (role)``."""
    who = cast.persona(role)
    _entry(run_id, f"## turn {turn:02d} — {who['name']}, {who['title']} ({role})", body)


def append_decision(run_id: str, *, body: str) -> None:
    """Append the chair's decision. The chair signs by name, not by role."""
    who = cast.persona(cast.CHAIR_ROLE)
    _entry(run_id, f"## decision — {who['name']}, {who['title']}", body)


def revised_path(run_id: str, artifact: str) -> Path:
    """Where the editable copy of ``artifact`` lives.

    Only the basename is used, so an artifact named by a nested or relative
    path still lands inside the run's own directory. ``revised`` is a component
    of the ``state_dir`` call, not a join onto its result, because ``state_dir``
    is what creates the directory (mode 0700).
    """
    return _config.state_dir("runs", run_id, "revised") / Path(artifact).name


def ensure_revised(run_id: str, artifact: str) -> Path:
    """Byte-copy the artifact into ``revised/`` if it is not already there.

    Called by ``seed`` of a junior-IC turn, so the worker only ever edits a
    file that already exists and the re-check has something to hash. Existing
    means the edit already happened: never overwrite it.
    """
    destination = revised_path(run_id, artifact)
    if not destination.exists():
        shutil.copyfile(artifact, destination)
    return destination


def digest(path) -> str:
    """SHA-256 hex of a file, or "" when it is absent or unreadable.

    The master-side re-check (spec 7) compares this before and after a junior-IC
    turn. An unreadable file is an unchanged one as far as the check goes, which
    is the honest reading: no evidence the edit landed.
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()
