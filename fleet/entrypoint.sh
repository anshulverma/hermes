#!/bin/sh
# Fleet worker container entrypoint. Installs throwaway SSH key from env and runs sshd in foreground.
set -e

if [ -n "${HERMES_AUTHORIZED_KEY}" ]; then
    mkdir -p /root/.ssh
    printf '%s\n' "${HERMES_AUTHORIZED_KEY}" > /root/.ssh/authorized_keys
    chmod 700 /root/.ssh
    chmod 600 /root/.ssh/authorized_keys
fi

# -D: foreground; -e: log to stderr (visible via `podman logs`).
exec /usr/sbin/sshd -D -e
