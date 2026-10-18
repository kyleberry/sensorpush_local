#!/usr/bin/env bash
# Runs once when the devcontainer is created (postCreateCommand).
set -euo pipefail

chsh -s "$(command -v zsh)"
uv sync --extra test
uv run activate-global-python-argcomplete

# Claude Code plugins from kyleberry/claude-plugins: kyle-dev (guard hook that
# blocks commits on main, terraform checks, pr-summary) and berry-mcp (the
# VictoriaLogs/VictoriaMetrics/Home Assistant MCP servers). ~/.claude/plugins
# isn't mounted from the host, since plugin caches are platform-specific, so
# they're installed here. The mounted settings.json already declares and
# enables both, and these commands leave it unchanged. Needs gitea.berry.house
# (home network or WireGuard); if it's unreachable, the container still comes
# up without the plugins.
if ! {
  claude plugin marketplace add https://gitea.berry.house/kyleberry/claude-plugins.git \
    && claude plugin install kyle-dev@kyle --scope user \
    && claude plugin install berry-mcp@kyle --scope user
}; then
  echo "warning: Claude Code plugins not installed; rerun .devcontainer/post-create.sh once gitea.berry.house is reachable" >&2
fi
