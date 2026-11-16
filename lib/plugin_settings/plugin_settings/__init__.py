"""Settings of the skills: one file, `config.yaml`, validated against one schema, and the data directory of each
plugin.

The file is the one set by `use`, else `$SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`; <config
dir> is `$CLAUDE_CONFIG_DIR`, else `~/.claude`. `load_config()` returns the typed `Config` (schema/), cached per
file version, and raises `ConfigFileError` with a line per problem, each naming its YAML path; `config()` exits
with that message instead. A missing file is `Config()`, every default. A setting is never read from the process
environment.

`Plugin.load()` returns `config()` and makes the process environment agree with it (`export`, `ENV_EXPORTS`):
proxies, CA files and Hugging Face settings that libraries and child processes read there, and the removal of the
variables the model client libraries read for keys, endpoints and headers.

<plugin data dir> is `$CLAUDE_PLUGIN_DATA` when set, else the directory Claude Code assigns: `<config
dir>/plugins/data/<plugin>-<marketplace>`, characters other than letters, digits, `_` and `-` replaced by `-`.
<plugin> is the `name` in the plugin's `.claude-plugin/plugin.json`; <marketplace> is the `name` in the
`.claude-plugin/marketplace.json` of the nearest directory above the plugin (a plugin loaded in place), else the
marketplace directory of a cache copy (`<config dir>/plugins/cache/<marketplace>/<plugin>/<version>`). A skill
binds to its plugin with `Plugin.of(__file__)`.
"""

from .env_export import CLEARED_KEYS, CLEARED_PREFIXES, ENV_EXPORTS, EnvVar, export
from .loader import SETUP_LINE, ConfigFileError, config, error, load_config
from .old_keys import old_key_errors
from .paths import CONFIG_ENV, config_dir, config_file, display, use
from .plugin import MANIFEST, Plugin
from .schema import *  # noqa: F403
from .schema import __all__ as _schema_all

__all__ = [
    "CLEARED_KEYS", "CLEARED_PREFIXES", "CONFIG_ENV", "ENV_EXPORTS", "MANIFEST", "SETUP_LINE", "ConfigFileError",
    "EnvVar", "Plugin", "config", "config_dir", "config_file", "display", "error", "export", "load_config",
    "old_key_errors", "use", *_schema_all,
]
