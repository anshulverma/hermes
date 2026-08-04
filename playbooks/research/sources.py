"""Item sources for the research playbook, plus the built-in ``config`` source.

An item source is a callable ``fn(config: dict) -> list[dict]`` registered under a
name. Each item it returns carries at least ``id`` (stable, unique within the run,
and safe to embed in a ticket id), ``title`` (a short human label), and ``context``
(the text block describing the item, which is handed to the agent). Extra keys ride
along untouched, so a source can carry whatever its report needs.

Sources are discovered like every other adapter: the module defining one is imported
for its registration side-effect. Sources that shell out to host-specific tooling
belong in the host's private adapter directory, not here.

The built-in ``config`` source reads items straight out of the run configuration, so
the playbook is usable and testable with no external source at all.

Stdlib-only.
"""
from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

# Everything outside this set is replaced in an item id, so an id is always safe
# to embed in a ticket id and in a filesystem path.
_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


@runtime_checkable
class ItemSource(Protocol):
    """The item-source interface. The signature is load-bearing."""

    def __call__(self, config: dict) -> list[dict]: ...


# --- registry ------------------------------------------------------------

_REGISTRY: dict[str, "ItemSource"] = {}


def register(name: str, fn: "ItemSource") -> None:
    """Register an item source under a name (last write wins)."""
    _REGISTRY[name] = fn


def load(name: str) -> "ItemSource":
    """Resolve a registered item source by name.

    Raises:
        KeyError: if no source is registered under `name`.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(
            f"unknown item source {name!r}; registered sources: {known}. "
            f"Import the module that registers it first."
        ) from None


# --- helpers -------------------------------------------------------------


def safe_id(value: Any, fallback: str) -> str:
    """Return a ticket-id-safe form of `value`, or `fallback` when it is empty."""
    text = str(value).strip() if value is not None else ""
    cleaned = _UNSAFE_ID_CHARS.sub("_", text).strip("_")
    return cleaned or fallback


# --- the built-in config source ------------------------------------------


def config_source(config: dict) -> list[dict]:
    """Read items from the run configuration.

    ``items`` is used when present: a list of dicts (or bare strings). Otherwise
    each ``goals`` line becomes one item whose title and context are the line
    itself. An item that already carries an id keeps it; the rest are numbered.
    """
    raw = config.get("items")
    if raw is None:
        raw = config.get("goals") or []
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        return []

    items: list[dict] = []
    for index, entry in enumerate(raw, start=1):
        fallback = f"item-{index}"
        if isinstance(entry, dict):
            item = dict(entry)
            item["id"] = safe_id(item.get("id"), fallback)
            item.setdefault("title", item["id"])
            item.setdefault("context", item["title"])
        else:
            text = str(entry).strip()
            if not text:
                continue
            item = {"id": fallback, "title": text, "context": text}
        items.append(item)
    return items


register("config", config_source)
