# plugin_settings

`lib/plugin_settings` reads the settings file `config.yaml` of every skill, resolves each plugin's data directory, and
holds the lookup of the extra CA that the TLS code of ai_models adds to its trust. The file, its
sections, every setting and the error messages are documented for users in the `setup:settings` skill; its template
is `plugins/setup/skills/settings/assets/config.example.yaml`.

## The settings file

One file for all plugins: `$SKILLS_CONFIG` when set, else `<config dir>/plugins/data/config.yaml`, where `<config
dir>` is `$CLAUDE_CONFIG_DIR`, else `~/.claude`. `use(path)` sets another file for the process. `read_config()`
returns the parsed file, `{}` when the file is missing or empty, and raises `ConfigFileError` when it is not valid
YAML or not a mapping. ai_models reads its sections (`providers`, `models`, `diffusers`) through the same two calls
(`docs/ai_models.md`), so there is one file and one loader.

The fourth section, `settings`, holds every other setting as `KEY: value`, with the setting names the skills used
before (`HF_HOME`, `EXTRA_CA_CERT`, ...). It is flat: no setting name is read by two plugins
with two meanings. `settings()` returns it as strings: a YAML boolean becomes `true` or `false`, a number its text,
and a key with no value (null) is left out. A list or mapping value, or a `settings` that is not a mapping, exits
with an error naming the file.

## Reading a setting

`get(key, default)` returns `settings.<key>` of the file, else the variable `key` of the process environment, else
`default`. The environment stays a source so that a variable exported in the user's shell (`HF_TOKEN`,
`SSL_CERT_FILE`) and the variables the tests pass to a child process still apply; the file wins over it. Skills read
every setting through `get` (or `Plugin.get`), never from `os.environ`.

`require(key)` returns the value stripped of whitespace and treats an empty or blank value as missing, so `KEY: ""`
in the file unsets an exported key for the skill. A missing key exits with a message that names the file (with `~`
for the home directory), says whether it exists, and shows the two lines to add. `invalid(key, value, expected)`
exits naming `settings.<key>` of the file, or the process environment, as the place the value came from. Both end
with a line naming `setup:settings`. `Plugin.require`, `Plugin.invalid` and `Plugin.get` are the same calls.

## Export to the environment

`Plugin.load()` reads the file, exits on a malformed one, and copies the settings of `ENV_KEYS` that the file sets
into `os.environ`, over a process value. These are the settings that code outside the skills reads from the
environment:

| Setting | Read there by |
|---|---|
| `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` | httpx and requests of ai_models (model calls and weight downloads) |
| `SSL_CERT_FILE` | the default TLS verification of libraries outside ai_models, which uses certifi's roots plus `EXTRA_CA_CERT` |
| `NODE_EXTRA_CA_CERTS` | Node.js child processes (short-video) |
| `HF_HOME`, `HF_TOKEN` | huggingface_hub, for the weights of the `diffusers` models |

No other setting is exported. `EXTRA_CA_CERT` is read by `ca` through `get`. A skill calls `Plugin.load()` at the
start of its CLI, before it imports a library that reads one of these variables at import time (huggingface_hub reads `HF_HOME`).

The file never sets `CLAUDE_CONFIG_DIR`, `CLAUDE_PLUGIN_DATA` or `SKILLS_CONFIG`: they decide where the file and the
data directory are, so the code reads them from the process environment only.

## Binding to a plugin

A skill calls `Plugin.of(__file__)`, which takes the plugin from the nearest `.claude-plugin/plugin.json` above the
file. The plugin name is read from that manifest, not from the directory, because a cache copy under `<config
dir>/plugins/cache/<marketplace>/<plugin>/<version>` sits in a directory named after the version.

## Data directory

`Plugin.load()` also makes its plugin the process's plugin: `data_dir()` returns that plugin's data directory, else
`$CLAUDE_PLUGIN_DATA`, else None. A shared package uses it for data of the calling skill (`ai_models.weights`: the
default weights directory).

Without `CLAUDE_PLUGIN_DATA`, the data directory is the one Claude Code assigns to the plugin, `<config
dir>/plugins/data/<plugin>-<marketplace>`. The marketplace name has two sources:

- A plugin loaded in place from a directory marketplace has `.claude-plugin/marketplace.json` above it, whose `name`
  is used.
- A cache copy holds only the plugin directory, so no marketplace manifest is above it; the marketplace is the
  directory name in the cache layout.

When neither gives a name, or the plugin manifest has no name, the lookup exits asking for `CLAUDE_PLUGIN_DATA`
instead of guessing a directory Claude Code would not use. `plugin_env` in each plugin's `lib/uv_env.sh` resolves the
same directory in shell (`docs/architecture.md`).

## Extra CA

A TLS-intercepting proxy re-signs HTTPS traffic with its own root CA. The user exports that root
CA to a PEM file and names it in the setting `EXTRA_CA_CERT`. `ca.ca_cert()` returns the first of `CA_CERT_KEYS`
(`EXTRA_CA_CERT`, then `NODE_EXTRA_CA_CERTS`, each through `get`) that names an existing file, else None. With None,
callers keep the default trust. ai_models adds the CA to certifi's roots (`docs/ai_models.md`). The package ships no CA file and keeps no per-skill CA setting.

`SSL_CERT_FILE` is not read by `ca`. Python's default `ssl` context reads it, so httpx or requests with
their default verification use it as the whole trust store. ai_models does not: its context starts from certifi.
