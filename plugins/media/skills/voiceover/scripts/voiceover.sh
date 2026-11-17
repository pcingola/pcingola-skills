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
# The `cuda` extra (the CUDA build of torch on Linux, and fish-speech) when the settings file config.yaml has a
# provider of kind fish, which runs Fish Audio's model on the GPU in this process; else the `cpu` extra
CONFIG="${SKILLS_CONFIG:-$(_config_dir)/plugins/data/config.yaml}"
EXTRA="--extra cpu"
if grep -qsE '^[^#]*kind:[[:space:]]*.?fish\b' "${CONFIG/#\~/$HOME}"; then EXTRA="--extra cuda"; fi
exec uv run --project "$SCRIPT_DIR" $EXTRA python -m voiceover_tool "$@"
