"""No-ship guard shims — shared across LocalSite and DevserverSite.

Guard shims shadow real binaries and refuse land/push subcommands (exit 97),
passing everything else through to the real binary's absolute path.

Stdlib-only.
"""

# No-ship guard shims: each shim shadows a real binary and refuses the
# land/push subcommands (log + non-zero exit), passing everything else through to
# the real binary. Maps shim name -> the subcommands it BLOCKS.
GUARD_SHIMS: dict[str, tuple[str, ...]] = {
    "git": ("push",),
    "sl": ("push", "land"),
    "hg": ("push",),
    "jf": ("land",),
    "arc": ("land",),
}

# Non-zero exit code a guard shim uses when it blocks a land/push.
GUARD_BLOCK_EXIT = 97


def render_shim_script(name: str, blocked: tuple[str, ...], real_path: str | None) -> str:
    """Render a POSIX-sh guard shim script.

    Args:
        name: Command name (e.g. "git")
        blocked: Subcommands to block (e.g. ("push",))
        real_path: Absolute path to the real binary (from `which` or `command -v`),
                   or None if binary is absent.

    Returns:
        str: The complete shell script content (#!/bin/sh ...)

    The script blocks the specified subcommands (exit 97), and passes everything
    else through to the real binary via 'exec "<realpath>" "$@"'. When real_path
    is None (binary absent), the script fails closed (exit 127) instead of recursing.
    """
    cases = "|".join(blocked)

    if real_path:
        passthrough = f'exec "{real_path}" "$@"'
    else:
        # Real binary absent: never recurse back into the shim; fail closed.
        passthrough = (
            f'echo "[hermes-no-ship-guard] real {name!r} not found" >&2; exit 127'
        )

    script = f"""#!/bin/sh
# hermes no-ship guard shim for {name!r}: blocks {cases}
for _arg in "$@"; do
  case "$_arg" in
    {cases})
      echo "[hermes-no-ship-guard] blocked '{name} $_arg' (no-land/no-push invariant)" >&2
      exit {GUARD_BLOCK_EXIT}
      ;;
  esac
done
{passthrough}
"""
    return script
