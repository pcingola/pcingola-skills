#!/bin/bash -eu
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# Prevent a parent venv from overriding uv's --project venv
unset VIRTUAL_ENV
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
# The plugin directory: the nearest directory above holding .claude-plugin/plugin.json
PLUGIN_ROOT="$SCRIPT_DIR"
until [ -f "$PLUGIN_ROOT/.claude-plugin/plugin.json" ] || [ "$PLUGIN_ROOT" = / ]; do
    PLUGIN_ROOT="$(dirname "$PLUGIN_ROOT")"
done
# uv environment outside the plugin directory (lib/uv_env.sh)
source "$PLUGIN_ROOT/lib/uv_env.sh"
plugin_env "$SCRIPT_DIR"
exec uv run --project "$SCRIPT_DIR" python -m second_opinion_tool "$@"
