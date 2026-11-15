"""Unit tests for plugin_settings: plugin and marketplace names, data directory,
the config file, `get`, `require`, `invalid` and the export of ENV_KEYS.

plugin_settings reads HOME, CLAUDE_CONFIG_DIR, CLAUDE_PLUGIN_DATA, SKILLS_CONFIG
and the config file, and Plugin.load writes os.environ. Every test that depends
on the environment runs the real code in a child process with an explicit
environment (tests/subproc.py) and a real config file in a temp directory."""
import json
from pathlib import Path

import pytest

from plugin_settings import Plugin
from tests.subproc import child_env, run_python

KEY = "PLUGIN_SETTINGS_TEST_KEY"


@pytest.fixture
def home(tmp_path) -> Path:
    """An empty home directory; the child processes get HOME set to it and nothing else."""
    (tmp_path / "home").mkdir()
    return tmp_path / "home"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_plugin(root: Path, name: str = "demo") -> Plugin:
    write(root / ".claude-plugin" / "plugin.json", json.dumps({"name": name}))
    code = root / "skills" / "s" / "scripts" / "s_tool"
    code.mkdir(parents=True)
    return Plugin.of(code / "config.py")


@pytest.fixture
def plugin(tmp_path):
    """Plugin `demo` in place in a directory marketplace named `mk`."""
    write(tmp_path / "mk" / ".claude-plugin" / "marketplace.json", json.dumps({"name": "mk"}))
    return make_plugin(tmp_path / "mk" / "plugins" / "demo")


def config_path(home: Path) -> Path:
    """The default config file under HOME."""
    return home / ".claude" / "plugins" / "data" / "config.yaml"


def run(home: Path, plugin: Plugin, body: str, **env: str):
    """Run `body` in a child process with HOME=home plus `env` and nothing else. `P` is `plugin`, and
    `out(v)` prints v as JSON. Returns the CompletedProcess."""
    root = "None" if plugin.root is None else f"Path({str(plugin.root)!r})"
    code = (
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "import plugin_settings\n"
        "from plugin_settings import Plugin\n"
        f"P = Plugin({plugin.name!r}, {root})\n"
        "def out(v): print(json.dumps(v, default=str))\n"
        + body
    )
    return run_python(code, child_env({"HOME": str(home), **env}))


def value(done) -> object:
    """The JSON value the child printed last; fails with the child's stderr when it exited non-zero."""
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


# Plugin, marketplace and data directory


def test_plugin_from_nearest_manifest(plugin, tmp_path):
    """Plugin.of takes the plugin name and root from the nearest .claude-plugin/plugin.json above a skill
    module. Guards the binding every skill makes with Plugin.of(__file__)."""
    assert plugin == Plugin("demo", tmp_path / "mk" / "plugins" / "demo")


def test_no_manifest(tmp_path):
    """Plugin.of returns Plugin(None, None) for a file with no plugin manifest above it. Guards the
    unknown-plugin case that data_dir turns into an error asking for CLAUDE_PLUGIN_DATA."""
    assert Plugin.of(tmp_path / "x.py") == Plugin(None, None)


def test_data_dir_in_place(home, plugin):
    """Plugin.data_dir and config_file for a plugin loaded in place: `<config
    dir>/plugins/data/<plugin>-<marketplace>` with the marketplace from the marketplace.json above, and
    `<config dir>/plugins/data/config.yaml`. Guards the directory Claude Code assigns, which uv_env.sh must
    match."""
    got = value(run(home, plugin, "out([str(P.data_dir()), str(plugin_settings.config_file())])"))
    assert got == [str(home / ".claude" / "plugins" / "data" / "demo-mk"), str(config_path(home))]


def test_data_dir_of_cache_copy(home):
    """Plugin.data_dir of a cache copy takes the marketplace from
    `plugins/cache/<marketplace>/<plugin>/<version>`. Guards plugins installed from a git or remote
    marketplace, which have no marketplace.json above them."""
    p = make_plugin(home / ".claude" / "plugins" / "cache" / "mk2" / "demo" / "0123abcd")
    assert value(run(home, p, "out(str(P.data_dir()))")) == str(home / ".claude" / "plugins" / "data" / "demo-mk2")


def test_claude_config_dir(home, tmp_path):
    """Plugin.data_dir, the cache layout and the config file follow CLAUDE_CONFIG_DIR. Guards users who move
    Claude Code's configuration directory."""
    p = make_plugin(tmp_path / "cfg" / "plugins" / "cache" / "mk" / "demo" / "v1")
    got = value(run(home, p, "out([str(P.data_dir()), str(plugin_settings.config_file())])",
                    CLAUDE_CONFIG_DIR=str(tmp_path / "cfg")))
    assert got == [str(tmp_path / "cfg" / "plugins" / "data" / "demo-mk"),
                   str(tmp_path / "cfg" / "plugins" / "data" / "config.yaml")]


def test_data_id_sanitised(home, tmp_path):
    """Plugin.data_dir replaces characters other than letters, digits, `_` and `-` in `<plugin>-<marketplace>`
    with `-`. Guards agreement with the directory name Claude Code assigns."""
    write(tmp_path / "m" / ".claude-plugin" / "marketplace.json", json.dumps({"name": "my.market"}))
    p = make_plugin(tmp_path / "m" / "plugins" / "a b", name="a b")
    assert value(run(home, p, "out(P.data_dir().name)")) == "a-b-my-market"


def test_unknown_marketplace_exits(home, tmp_path):
    """Plugin.data_dir exits 1 with `cannot tell the marketplace` for a plugin with no marketplace manifest
    above it and outside the cache layout. Guards against guessing a data directory Claude Code does not
    use."""
    p = make_plugin(tmp_path / "loose" / "demo")
    done = run(home, p, "P.data_dir()")
    assert done.returncode == 1
    assert "cannot tell the marketplace" in done.stderr


def test_claude_plugin_data_wins(home, tmp_path):
    """Plugin.data_dir uses CLAUDE_PLUGIN_DATA when set, even when the marketplace is unknown. Guards the
    override Claude Code sets and the error messages ask for."""
    p = make_plugin(tmp_path / "loose" / "demo")
    assert value(run(home, p, "out(str(P.data_dir()))", CLAUDE_PLUGIN_DATA=str(tmp_path / "pd"))) == str(tmp_path / "pd")


def test_blank_claude_plugin_data_is_ignored(home, plugin):
    """Plugin.data_dir treats a whitespace-only CLAUDE_PLUGIN_DATA as unset. Guards against a data directory
    named by blanks."""
    got = value(run(home, plugin, "out(str(P.data_dir()))", CLAUDE_PLUGIN_DATA="  "))
    assert got == str(home / ".claude" / "plugins" / "data" / "demo-mk")


def test_no_name_exits(home):
    """Plugin.data_dir exits 1 asking to set CLAUDE_PLUGIN_DATA when the plugin name is unknown. Guards the
    error path of a module outside any plugin."""
    done = run(home, Plugin(None, None), "P.data_dir()")
    assert done.returncode == 1
    assert "set CLAUDE_PLUGIN_DATA" in done.stderr


# The config file and get


def test_skills_config_names_another_file(home, plugin, tmp_path):
    """SKILLS_CONFIG names the config file in place of the default. Guards the override the tests and the
    wrappers use."""
    write(config_path(home), f"settings: {{{KEY}: default}}\n")
    write(tmp_path / "other.yaml", f"settings: {{{KEY}: other}}\n")
    got = value(run(home, plugin, f"out([str(plugin_settings.config_file()), P.get({KEY!r})])",
                    SKILLS_CONFIG=str(tmp_path / "other.yaml")))
    assert got == [str(tmp_path / "other.yaml"), "other"]


def test_get_file_then_default(home, plugin):
    """get returns settings.<key> of the file, else the default when the file lacks the key or holds it empty
    (null). Guards the documented order."""
    body = f"out([P.get({KEY!r}), P.get('NULL_KEY', 'dflt'), P.get('NONE_KEY', 'dflt'), P.get('NONE_KEY')])"
    write(config_path(home), f"settings:\n  {KEY}: file\n  NULL_KEY:\n")
    assert value(run(home, plugin, body)) == ["file", "dflt", "dflt", None]


def test_environment_variable_of_a_setting_is_ignored(home, plugin):
    """get, require and ca_cert ignore a process environment variable named like a setting, with and without
    a config file; Plugin.load removes an exported ENV_KEYS variable the file does not set. Guards
    config.yaml as the only source of a setting."""
    ca = home / "ca.pem"
    write(ca, "pem")
    env = {KEY: "env", "NULL_KEY": "env", "EXTRA_CA_CERT": str(ca), "HF_TOKEN": "env-tok"}
    body = (f"P.load(); from plugin_settings.ca import ca_cert\n"
            f"out([P.get({KEY!r}), P.get('NULL_KEY', 'dflt'), ca_cert(), os.environ.get('HF_TOKEN')])")
    assert value(run(home, plugin, body, **env)) == [None, "dflt", None, None]
    write(config_path(home), "settings:\n  NULL_KEY:\n")
    assert value(run(home, plugin, body, **env)) == [None, "dflt", None, None]
    done = run(home, plugin, f"P.require({KEY!r})", **env)
    assert done.returncode == 1
    assert f"{KEY} is not set" in done.stderr


def test_values_are_strings(home, plugin):
    """get returns YAML booleans as `true`/`false` and numbers as their text. Guards callers that parse a
    boolean setting from a string."""
    write(config_path(home), "settings: {A: true, B: false, C: 3, D: ~/x}\n")
    assert value(run(home, plugin, "out([P.get(k) for k in 'ABCD'])")) == ["true", "false", "3", "~/x"]


def test_no_file_no_settings(home, plugin):
    """Without a config file, get returns the default and Plugin.load changes nothing in an environment without
    ENV_KEYS or client-library variables, and creates no file. Guards a first run before setup:settings."""
    before = value(run(home, plugin, "out(dict(os.environ))"))
    assert value(run(home, plugin, "P.load(); out(dict(os.environ))")) == before
    assert value(run(home, plugin, f"out(P.get({KEY!r}, 'dflt'))")) == "dflt"
    assert not config_path(home).exists()


def test_load_sets_env_keys_from_the_file_only(home, plugin):
    """Plugin.load sets each variable of ENV_KEYS from the file (over the process value; proxies also in lower
    case), removes those the file does not set in both cases, removes the client-library variables of
    CLEARED_PREFIXES and CLEARED_KEYS, exports no other setting and keeps unrelated variables. Guards that a shell
    variable is never a setting (docs/plugin_settings.md, "Export to the environment")."""
    write(config_path(home), f"settings: {{HF_TOKEN: tok, SSL_CERT_FILE: /ca.pem, HTTPS_PROXY: http://p:1, {KEY}: v}}\n")
    names = ["HF_TOKEN", "SSL_CERT_FILE", "HTTPS_PROXY", "https_proxy", "HF_HOME", "HTTP_PROXY", "http_proxy",
             "no_proxy", "OPENAI_API_KEY", "GOOGLE_API_KEY", KEY, "UNRELATED"]
    shell = {"SSL_CERT_FILE": "/process.pem", "https_proxy": "http://shell:1", "HF_HOME": "/shell/hf",
             "HTTP_PROXY": "http://shell:2", "http_proxy": "http://shell:2", "no_proxy": "shell",
             "OPENAI_API_KEY": "shell", "GOOGLE_API_KEY": "shell", "UNRELATED": "kept"}
    got = value(run(home, plugin, f"P.load(); out({{k: os.environ.get(k) for k in {names!r}}})", **shell))
    assert got == {"HF_TOKEN": "tok", "SSL_CERT_FILE": "/ca.pem", "HTTPS_PROXY": "http://p:1",
                   "https_proxy": "http://p:1", "HF_HOME": None, "HTTP_PROXY": None, "http_proxy": None,
                   "no_proxy": None, "OPENAI_API_KEY": None, "GOOGLE_API_KEY": None, KEY: None, "UNRELATED": "kept"}


def test_path_keys_in_settings_have_no_effect(home, plugin, tmp_path):
    """CLAUDE_PLUGIN_DATA in `settings` does not move the data directory, and Plugin.load does not export it.
    Guards against the file moving the directories it decides."""
    write(config_path(home), f"settings: {{CLAUDE_PLUGIN_DATA: {tmp_path / 'elsewhere'}}}\n")
    got = value(run(home, plugin, "P.load(); out(['CLAUDE_PLUGIN_DATA' in os.environ, str(P.data_dir())])"))
    assert got == [False, str(home / ".claude" / "plugins" / "data" / "demo-mk")]


@pytest.mark.parametrize("text, message", [
    ("a: [", "is not valid YAML"),
    ("- a\n", "must be a mapping"),
    ("settings: [a]\n", "`settings` in ~/.claude/plugins/data/config.yaml must be a mapping"),
    ("settings: {A: [1]}\n", "settings.A in ~/.claude/plugins/data/config.yaml must be a single value"),
])
def test_malformed_file_exits(home, plugin, text, message):
    """Plugin.load exits 1 naming the file for a malformed config file. Guards a clear message instead of a
    traceback."""
    write(config_path(home), text)
    done = run(home, plugin, "P.load()")
    assert done.returncode == 1
    assert message in done.stderr


# require and invalid


def test_require_present(home, plugin):
    """require returns the value stripped of whitespace. Guards settings with stray spaces."""
    write(config_path(home), f"settings: {{{KEY}: ' v '}}\n")
    assert value(run(home, plugin, f"out(P.require({KEY!r}))")) == "v"


def test_require_empty_value_is_missing(home, plugin):
    """require treats an empty or blank value in the file as missing. Guards that `KEY: ""` does not pass as
    set."""
    write(config_path(home), f"settings: {{{KEY}: '  '}}\n")
    done = run(home, plugin, f"P.require({KEY!r})")
    assert done.returncode == 1
    assert f"{KEY} is not set" in done.stderr


def test_require_missing_names_the_file(home, plugin):
    """The error for a missing key names the config file with found/not found and `~`, and the lines to add.
    Guards the message users follow to fix a missing setting."""
    done = run(home, plugin, f"plugin_settings.require({KEY!r})")
    assert done.returncode == 1
    assert done.stderr == (
        f"Error: {KEY} is not set.\n"
        "Settings are read from ~/.claude/plugins/data/config.yaml (not found), section `settings`.\n"
        f"Add it to that file:\n  settings:\n    {KEY}: <value>\n"
        "The setup:settings skill describes every setting and creates the file.\n"
    )


def test_invalid_names_the_setting_in_the_file(home, plugin):
    """invalid names `settings.<key>` of the config file. Guards that the error names the place to fix."""
    write(config_path(home), f"settings: {{{KEY}: b}}\n")
    done = run(home, plugin, f"P.invalid({KEY!r}, P.get({KEY!r}), 'a number')")
    assert done.returncode == 1
    assert done.stderr == (
        f"Error: {KEY}='b' (settings.{KEY} in ~/.claude/plugins/data/config.yaml) is not valid: a number.\n"
        "The setup:settings skill describes every setting and creates the file.\n")
