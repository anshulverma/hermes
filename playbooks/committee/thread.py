"""The committee's transcript, and the one file a worker may edit.

``thread.md`` is the whole channel: it is what every worker reads before it
speaks and what a human reads afterwards. It is append-only -- opened ``"a"``,
flushed per call, no temp file and no locking -- because the master writes it
from one process, one settled turn at a time. A turn that produced no finding
still gets an entry (``NO_TURN``), so the transcript stays contiguous and the
loss is visible rather than silently missing.

Then ``revised/``: a byte copy of the document as ``open`` read it, made once,
that the junior IC edits when the owner delegates. The original is never
touched, and ``digest`` is what lets ``reduce`` tell whether the edit actually
landed.

And ``doc/``: every version of the document, for the view's stepper --
``doc/00-original<ext>`` (the bytes ``open`` hashed) and ``doc/tNN<ext>`` (the
revised copy as junior-IC turn NN left it), written atomically and 0600 by
``write_snapshot`` and read back by ``read_regular``, which follows no symlink.

And ``takes/``: the body of each take the rules sent back
(``takes/<base>-take<n>.md``, 0600), written by the master with ``write_take``
so the retake can reread what it said. The server never serves it.

Stdlib-only.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
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


# The header line naming the artifact; `header_artifact` reads it back. Plain,
# like every voice-era label; a thread written before voice has the bold form,
# and a pre-voice run still open reads it back too.
_ARTIFACT_LINE = "Artifact: "
_ARTIFACT_LINES = (_ARTIFACT_LINE, "**Artifact:** ")


def write_header(
    run_id: str, *, charge: str, artifact: str, roster: list[str],
    rules: tuple[str, ...] = (),
) -> None:
    """Open the transcript with the charge, the artifact path, the roster and the ground rules.

    Plain labels, no bold: the header is the first thing every speaker reads,
    and it is held to the rules it states. ``rules`` follow the roster after a
    blank line, one per line, so every later speaker has them in the thread.
    """
    lines = [
        f"# Committee — {run_id}",
        "",
        f"Charge: {charge}",
        "",
        f"{_ARTIFACT_LINE}{artifact}",
        "",
        "Committee:",
        "",
    ]
    lines.extend(f"- {member}" for member in roster)
    if rules:
        lines.extend(["", "Ground rules for every speaker:", *rules])
    _append(run_id, "\n".join(lines) + "\n")


def header_artifact(run_id: str) -> str:
    """The artifact path the header names, or "". Creates nothing.

    For the view, before the first turn settles: until then no reduction names
    the file, and the header -- written by ``open`` -- is all thread.md holds.
    A symlinked thread.md is not followed (``read_regular``). Both label forms
    are read: plain since voice, bold before it.
    """
    data = read_regular(run_file(run_id, "thread.md")) or b""
    for line in data.decode("utf-8", "replace").splitlines():
        for label in _ARTIFACT_LINES:
            if line.startswith(label):
                return line[len(label):].strip()
    return ""


def _plain_dir(run_id: str, name: str, *, create: bool = True) -> Path:
    """``runs/<run_id>/<name>/`` at 0700, refusing a symlink or a file planted there.

    Every worker runs bypassPermissions and can leave either. ``state_dir``
    would follow the symlink (and chmod its target). Raise instead.
    ``create=False`` only looks: it makes and chmods nothing, and raises
    ``FileNotFoundError`` when the folder is absent.
    """
    folder = _config.resolve_home() / "runs" / run_id / name
    try:
        mode = os.lstat(folder).st_mode
    except FileNotFoundError:
        if not create:
            raise
        mode = stat.S_IFDIR
    if not stat.S_ISDIR(mode):
        raise ValueError(f"{folder} is not a plain directory (a symlink or a file); refusing it")
    return _config.state_dir("runs", run_id, name) if create else folder


def images_dir(run_id: str, *, create: bool = True) -> Path:
    """``runs/<run_id>/images/``: the one folder an owner or reviewer may write an image into (0700).

    A planted symlink or file is refused (``_plain_dir``): a file check through
    a symlink could pass an image the server, which follows none, then refuses.

    ``create=False`` only looks (reduce grading a take): it makes and chmods
    nothing, and raises ``FileNotFoundError`` when the folder is absent.
    """
    return _plain_dir(run_id, "images", create=create)


def takes_dir(run_id: str) -> Path:
    """``runs/<run_id>/takes/`` (0700): each discarded take's body, for its retake to reread.

    Written by the master only, never served. A planted symlink or file is
    refused (``_plain_dir``), so a take is never written through one.
    """
    return _plain_dir(run_id, "takes")


def write_take(run_id: str, name: str, body: str) -> str:
    """Write one discarded take's body to ``runs/<run_id>/takes/<name>``; return ``takes/<name>``.

    Atomic, 0600 and overwriting, like ``write_snapshot``: ``os.replace``
    swaps out a symlink planted at the name rather than writing through it.

    Raises:
        ValueError: ``name`` is not a plain file name, or the folder is refused.
        OSError: the write failed.
    """
    if Path(name).name != name or name in ("", ".", ".."):
        raise ValueError(f"not a take file name: {name!r}")
    _write_private(takes_dir(run_id), name, body.encode("utf-8"))
    return f"takes/{name}"


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

    An artifact whose basename is empty or ``..`` -- ``""``, ``"/"``, ``"."``,
    a trailing slash -- would return the DIRECTORY instead of a file in it:
    ``ensure_revised`` would then see it already exists and skip the copy, and
    ``digest`` of a directory is ``""``, so every re-check would report
    ``verified: false`` with no error anywhere. Raise instead.

    A newline anywhere in the path is refused for a different reason: the path
    is written verbatim into the thread header and into every goal, both of
    which are line-oriented, so one would split the header across two lines and
    forge an entry. ``seed`` calls this before ``write_header``, so the refusal
    lands before anything is written.

    Raises:
        ValueError: ``artifact`` has no usable filename.
    """
    name = Path(artifact).name
    if not name or name == ".." or "\n" in artifact:
        raise ValueError(f"artifact has no usable filename: {artifact!r}")
    return _config.state_dir("runs", run_id, "revised") / name


def ensure_revised(run_id: str, artifact: str, digest: str) -> tuple[Path, str | None]:
    """Create the editable copy in ``revised/`` if it is not already there.

    Its bytes are doc/00-original's when that file still holds what ``open``
    read -- its sha256 is ``digest``, the one ``open`` took -- and otherwise the
    live artifact's. Called by ``seed`` of a junior-IC turn, so the worker only
    ever edits a file that already exists and the re-check has something to
    hash. Existing means the edit already happened: never overwrite it.

    Returns:
        The copy's path, and a ``snapshot: …`` note when this call copied the
        live artifact because doc/00-original was not the file ``open`` wrote;
        None when it used the snapshot or copied nothing.

    Raises:
        OSError: no copy could be made -- doc/00-original and the artifact are
            both unreadable, or writing into ``revised/`` failed.
    """
    destination = revised_path(run_id, artifact)
    if destination.exists():
        return destination, None
    # The open-time snapshot, so Edit 1's baseline is exactly what the committee
    # was handed even if the original moved since. But every worker runs
    # bypassPermissions and can delete doc/00-original, swap it for a symlink
    # or rewrite it -- and nothing else re-checks it, where `artifact_intact`
    # does re-check the live file. So only the bytes `open` hashed are used;
    # anything else copies the live file and says so. `read_regular`, not
    # `is_file()`: a symlink there is refused, not followed.
    key = snapshot_key(artifact, None)
    handed = read_regular(run_file(run_id, key))
    if handed is not None and hashlib.sha256(handed).hexdigest() == digest:
        destination.write_bytes(handed)
        return destination, None
    shutil.copyfile(artifact, destination)
    return destination, (
        f"snapshot: {key} is not the file open wrote, so the revised copy was made "
        f"from the live artifact"
    )


def digest(path) -> str:
    """SHA-256 hex of a file, or "" when it is absent or unreadable.

    The master-side re-check (spec 7) compares this before and after a junior-IC
    turn. An unreadable file is an unchanged one as far as the check goes, which
    is the honest reading: no evidence the edit landed.

    ``TypeError``/``ValueError`` as well as ``OSError``: this is called from
    ``reduce``, which must never raise, and ``Path(None)`` is a ``TypeError``
    rather than an ``OSError``.
    """
    try:
        data = Path(path).read_bytes()
    except (OSError, TypeError, ValueError):
        return ""
    return hashlib.sha256(data).hexdigest()


# --- the document's versions (doc/) ------------------------------------------

# A suffix worth keeping on a snapshot's name: a dot and 1-16 alphanumerics.
# Anything else (none, "a.b c") is dropped, so every name the view emits is one
# the server's name pattern accepts.
_EXT = re.compile(r"\.[A-Za-z0-9]{1,16}")


def snapshot_key(artifact: str, turn: int | None) -> str:
    """The run-relative name of one version of the document.

    ``doc/00-original<ext>`` is the bytes ``open`` hashed; ``doc/tNN<ext>`` is
    the revised copy as junior-IC turn NN left it (``t100`` past 99: the cap has
    no upper bound, and steps are ordered by turn, never by file name). Pure, so
    the view and the backfill derive every name from (run, turn) and no path has
    to ride on a reduction.
    """
    suffix = Path(artifact).suffix
    ext = suffix if _EXT.fullmatch(suffix) else ""
    return f"doc/00-original{ext}" if turn is None else f"doc/t{turn:02d}{ext}"


def run_file(run_id: str, key: str) -> Path:
    """``runs/<run_id>/<key>`` under THIS process's HERMES_HOME. Creates nothing.

    Unlike ``path`` and ``revised_path``, which go through ``state_dir`` and so
    mkdir: the view calls this from a GET, and a GET must create nothing.
    """
    return _config.resolve_home() / "runs" / run_id / key


def read_regular(path) -> bytes | None:
    """The bytes of the regular file at ``path``, or None for anything else.

    ``O_NOFOLLOW``: a symlink is not the copy the worker was told to edit.
    ``O_NONBLOCK``: opening a FIFO must not hang ``reduce``. Never raises --
    ``reduce`` must not -- and ``os.open(None)`` is a TypeError, not an OSError.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except (OSError, TypeError, ValueError):
        return None
    # Check the raw fd before wrapping it, and always close it ourselves:
    # `open(fd)` on a directory raises without closing a caller-supplied fd,
    # and this runs in the long-lived master process.
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with open(fd, "rb", closefd=False) as handle:
            return handle.read()
    except OSError:
        return None
    finally:
        os.close(fd)


def write_snapshot(run_id: str, key: str, data: bytes) -> None:
    """Write ``data`` to ``runs/<run_id>/<key>``: atomic, private, overwriting.

    A 0600 temp file in the key's own 0700 directory, then ``os.replace``. The
    temp name is dot-prefixed, which the server's name pattern never matches, so
    a crashed write can never be served as a snapshot. It overwrites on purpose:
    a turn settled again keeps its last settle.

    Raises:
        ValueError: ``key`` is not ``doc/<name>`` -- an absolute or ``..`` key
            would write outside the run's doc/ directory.
    """
    target = Path(key)
    if target.parent != Path("doc") or target.name in ("", ".", ".."):
        raise ValueError(f"not a doc/ snapshot key: {key!r}")
    _write_private(_config.state_dir("runs", run_id, "doc"), target.name, data)


def _write_private(directory: Path, name: str, data: bytes) -> None:
    """``data`` to ``directory/name`` through a dot-prefixed 0600 temp file and ``os.replace``."""
    fd, temp = tempfile.mkstemp(dir=directory, prefix=f".{name}.")
    try:
        with open(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp, directory / name)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
