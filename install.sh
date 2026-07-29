#!/usr/bin/env bash
# Install Hermes Claude Code plugin by symlinking into ~/.claude/plugins/local
#
# This script is idempotent and can be run multiple times safely.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_PLUGINS_DIR="${HOME}/.claude/plugins/local"
PLUGIN_NAME="hermes"

echo "Installing Hermes Claude Code plugin..."

# Ensure the Claude plugins directory exists
mkdir -p "$CLAUDE_PLUGINS_DIR"

# Create symlink (or verify it's already correct)
PLUGIN_LINK="${CLAUDE_PLUGINS_DIR}/${PLUGIN_NAME}"
PLUGIN_SRC="${REPO_ROOT}/integrations/claude-code"

if [ -L "$PLUGIN_LINK" ]; then
    # Symlink exists - check if it points to the right place
    CURRENT_TARGET="$(readlink -f "$PLUGIN_LINK")"
    EXPECTED_TARGET="$(readlink -f "$PLUGIN_SRC")"

    if [ "$CURRENT_TARGET" = "$EXPECTED_TARGET" ]; then
        echo "✓ Plugin already installed: $PLUGIN_LINK -> $PLUGIN_SRC"
    else
        echo "⚠ Symlink exists but points elsewhere:"
        echo "  Current:  $CURRENT_TARGET"
        echo "  Expected: $EXPECTED_TARGET"
        echo "  Removing and recreating..."
        rm "$PLUGIN_LINK"
        ln -s "$PLUGIN_SRC" "$PLUGIN_LINK"
        echo "✓ Plugin installed: $PLUGIN_LINK -> $PLUGIN_SRC"
    fi
elif [ -e "$PLUGIN_LINK" ]; then
    echo "✗ Error: $PLUGIN_LINK exists but is not a symlink."
    echo "  Please remove it manually and re-run this script."
    exit 1
else
    # No symlink exists - create it
    ln -s "$PLUGIN_SRC" "$PLUGIN_LINK"
    echo "✓ Plugin installed: $PLUGIN_LINK -> $PLUGIN_SRC"
fi

echo ""
echo "Installation complete! The /hermes:* commands are now available in Claude Code."
echo "Run 'claude' to verify: you should see 'hermes' listed under available plugins."
