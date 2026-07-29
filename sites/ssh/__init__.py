"""sites.ssh — generic SSH site adapter.

A Site implementation that reaches worker hosts over SSH (agent-agnostic). This
is the foundation the future `meta`/`devserver` sites extend. Workers run only
sshd + the hermes worker runner + the configured agent + no-ship guard shims
(all baked into the image). Resource classes + counts come from per-host config.

Stdlib-only: subprocess, json, os, time.
"""
from sites.ssh.site import SSHSite  # noqa: F401

# Registration happens in site.py as a module-level side-effect.
