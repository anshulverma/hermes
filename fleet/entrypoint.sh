#!/bin/sh
# Hermes fleet worker entrypoint (fleet-integration-harness.md §2, §3).
#
# Installs the harness-provided throwaway public key into root's authorized_keys
# (hermetic auth: no baked credentials), then runs sshd in the foreground. The
# public key is passed at `podman run` time via $HERMES_AUTHORIZED_KEY.
set -e

if [ -n "${HERMES_AUTHORIZED_KEY}" ]; then
    mkdir -p /root/.ssh
    printf '%s\n' "${HERMES_AUTHORIZED_KEY}" > /root/.ssh/authorized_keys
    chmod 700 /root/.ssh
    chmod 600 /root/.ssh/authorized_keys
fi

# -D: foreground; -e: log to stderr (visible via `podman logs`).
exec /usr/sbin/sshd -D -e
