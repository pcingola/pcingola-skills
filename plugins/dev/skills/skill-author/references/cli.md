# CLI Skill Setup

A skill with executable code follows this repo's `scripts/` layout.

## Shell wrapper

Create `scripts/<skillname>.sh`:

```bash
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
# uv environment outside the plugin directory (the plugin's lib/uv_env.sh)
source "$PLUGIN_ROOT/lib/uv_env.sh"
plugin_env "$SCRIPT_DIR"
exec uv run --project "$SCRIPT_DIR" python -m <skillname>_tool "$@"
```

Then: `chmod +x scripts/<skillname>.sh`

`plugin_env` puts the skill's uv environment under `<plugin data dir>/env/` (`$CLAUDE_PLUGIN_DATA`, else `<config dir>/plugins/data/<plugin>-<marketplace>`, `<config dir>` being `$CLAUDE_CONFIG_DIR` or `~/.claude`) and exports its directory as `PLUGIN_ENV_DIR`. Each plugin with wrappers carries an identical copy of `lib/uv_env.sh` (`plugins/<plugin>/lib/uv_env.sh`). A `.venv` inside the plugin would sit in the loaded plugin directory and in every cache copy. Never run `uv run --project` on the skill directory without it; give a skill whose agent runs Python in its environment a passthrough in the wrapper (`<skillname>.sh python ...` forwarded to `uv run`).

## pyproject.toml

Create `scripts/pyproject.toml`:

```toml
[project]
name = "<skillname>-cli"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
```

A skill that reads settings depends on the repository's shared `plugin-settings` package (and a skill that calls a model on `ai-models` too) as git sources on branch `main`, like every other plugin project; the skill's `uv.lock` records the commit it resolved, and the repository's test runner moves it to the head of `main` before the skill's suite:

```toml
dependencies = ["plugin-settings"]

[tool.uv.sources]
plugin-settings = { git = "<origin URL>", subdirectory = "lib/plugin_settings", branch = "main" }
```

No path sources: a plugin's cache copy holds only the plugin directory.

## Python package

Create `scripts/<skillname>_tool/`:

**`__init__.py`** — can be empty or a one-line docstring.

**`__main__.py`**:

```python
from .<skillname> import main

main()
```

**`<skillname>.py`** (main module) — use argparse for subcommand dispatch:

```python
import argparse
import sys

def cmd_example(args):
    pass

def main():
    parser = argparse.ArgumentParser(prog="<skillname>")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("example", help="Do something")
    p.add_argument("input", help="Input file")
    p.set_defaults(func=cmd_example)
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)
```

For many subcommands, split into `cmd_*.py` modules with shared code in `common.py`.
