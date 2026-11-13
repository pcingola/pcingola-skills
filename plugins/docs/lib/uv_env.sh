# Sourced by every skill wrapper. Each plugin that
# has wrappers carries an identical copy in its lib/ directory.
#
# Claude Code loads a plugin from a directory marketplace in place and one
# from a git or remote marketplace from a copy of the plugin directory, ignored
# files included. Environments therefore live outside the plugin directory, in
# the plugin data directory: $CLAUDE_PLUGIN_DATA when set, else the directory
# Claude Code assigns, <config dir>/plugins/data/<plugin>-<marketplace> with
# characters other than letters, digits, `_` and `-` turned into `-`.
# <config dir> is $CLAUDE_CONFIG_DIR, else ~/.claude. <plugin> is the top-level
# "name" in .claude-plugin/plugin.json; <marketplace> the top-level "name" in the
# .claude-plugin/marketplace.json of the nearest directory above the plugin
# (loaded in place) when it has one, else the marketplace directory of a cache copy
# (<config dir>/plugins/cache/<marketplace>/<plugin>/<version>). plugin_env
# returns 1 when either name is unknown. The Python package plugin_settings
# resolves the same directory (tests/unit/plugin/test_manifest.py checks both).
#
#   <plugin data dir>/env/<parent id>/<project>/.venv       uv environment
#   <plugin data dir>/env/<parent id>/<project>/node/       short-video's node_modules
#   <plugin data dir>/env/<parent id>/<project>/pycache/    Python bytecode
#
# <parent id> is the POSIX cksum of the directory that holds the plugin
# directory. Plugins read in place resolve to the working tree's plugins/
# directory, so installed skills and wrappers run by hand share one set of
# environments. A plugin loaded from a cache copy (one
# subdirectory per version) would get its own environment, shared across its
# versions.
# <project> is the uv project's path inside the plugin without `skills/` and
# `/scripts`, with "/" turned into "-": `pptx`, `short-video-scripts-manim`.
# The path is kept short because espeak-ng (voiceover's kokoro backend) cannot
# open a data directory whose path is 160 characters or longer.
#
# plugin_env <uv project dir>
#   exports PLUGIN_ENV_DIR (the directory above), UV_PROJECT_ENVIRONMENT and
#   PYTHONPYCACHEPREFIX, so no __pycache__ is written into the plugin directory.

# Top-level "name" (two-space indent) of a JSON manifest; empty if none. The
# file test comes first: under `set -e -o pipefail` a failing sed would end
# the shell before the caller's error is printed.
_manifest_name() {
    if [ -f "$1" ]; then
        sed -n 's/^  "name":[[:space:]]*"\([^"]*\)".*/\1/p' "$1" | head -n 1
    fi
}

# $CLAUDE_CONFIG_DIR (a leading ~ expanded), else ~/.claude.
_config_dir() {
    local c="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    echo "${c/#\~/$HOME}"
}

# Marketplace of the plugin at $1 (physical path) named $2; empty if unknown.
_marketplace_name() {
    local d="$1" cache name=""
    while [ "$d" != / ]; do
        d="$(dirname "$d")"
        if [ -f "$d/.claude-plugin/marketplace.json" ]; then
            name="$(_manifest_name "$d/.claude-plugin/marketplace.json")"
            break
        fi
    done
    if [ -n "$name" ]; then
        echo "$name"
        return
    fi
    cache="$(_config_dir)/plugins/cache"
    if [ -d "$cache" ] && [ "$(basename "$(dirname "$1")")" = "$2" ] \
        && [ "$(cd "$(dirname "$(dirname "$(dirname "$1")")")" && pwd -P)" = "$(cd "$cache" && pwd -P)" ]; then
        basename "$(dirname "$(dirname "$1")")"
    fi
}

plugin_env() {
    local project plugin_root parent data rel id name market
    project="$(cd "$1" && pwd -P)"
    plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
    parent="$(dirname "$plugin_root")"
    id="$(printf '%s' "$parent" | cksum | cut -d' ' -f1)"
    rel="${project#"$plugin_root"/}"
    rel="${rel#skills/}"
    rel="${rel%/scripts}"
    if [ -n "${CLAUDE_PLUGIN_DATA:-}" ]; then
        data="$CLAUDE_PLUGIN_DATA"
    else
        # A cache copy's directory is named after the version, so the plugin
        # name comes from the manifest.
        name="$(_manifest_name "$plugin_root/.claude-plugin/plugin.json")"
        if [ -z "$name" ]; then
            echo "plugin_env: no top-level \"name\" in $plugin_root/.claude-plugin/plugin.json" >&2
            return 1
        fi
        market="$(_marketplace_name "$plugin_root" "$name")"
        if [ -z "$market" ]; then
            echo "plugin_env: cannot tell the marketplace of $plugin_root; set CLAUDE_PLUGIN_DATA" >&2
            return 1
        fi
        data="$(_config_dir)/plugins/data/$(printf '%s' "$name-$market" | tr -c 'A-Za-z0-9_-' '-')"
    fi
    export PLUGIN_ENV_DIR="$data/env/$id/${rel//\//-}"
    export UV_PROJECT_ENVIRONMENT="$PLUGIN_ENV_DIR/.venv"
    export PYTHONPYCACHEPREFIX="$PLUGIN_ENV_DIR/pycache"
}
