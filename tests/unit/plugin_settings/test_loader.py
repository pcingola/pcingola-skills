"""`plugin_settings.load_config` and `config` (docs/plugin_settings.md, loader): the missing file, malformed files,
the cache per file version, and the exit of `config()`."""

import os

import pytest

import plugin_settings
from plugin_settings import Config, ConfigFileError, load_config
from tests.settings_env import write_config
from tests.subproc import child_env, run_python


@pytest.fixture
def cfg_path(tmp_path):
    """A config path under tmp_path, set with `use` for this test only."""
    path = tmp_path / "config.yaml"
    plugin_settings.use(path)
    yield path
    plugin_settings.use(None)


def test_missing_or_empty_file_gives_defaults(cfg_path):
    """A missing file and an empty one load as `Config()`, every default. Guards a first run before
    setup:settings."""
    assert load_config() == Config()
    cfg_path.write_text("# only comments\n", encoding="utf-8")
    assert load_config() == Config()


@pytest.mark.parametrize("text, message", [("a: [", "is not valid YAML"), ("- a\n", "must be a mapping of sections")])
def test_invalid_yaml_and_non_mapping_fail(cfg_path, text, message):
    """A file that is not YAML or not a mapping is a ConfigFileError naming the file."""
    cfg_path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigFileError, match=message) as e:
        load_config()
    assert str(cfg_path) in str(e.value)


def test_cache_follows_the_file_version(cfg_path):
    """load_config returns the same object while the file's mtime and size stay, and reads the file again when
    either changes. Guards the long-running Studio server seeing edits, and every other call being a lookup."""
    write_config(cfg_path, studio={"dir": "/a"})
    first = load_config()
    assert load_config() is first
    st = cfg_path.stat()
    write_config(cfg_path, studio={"dir": "/b"})  # same size
    os.utime(cfg_path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    second = load_config()
    assert second is not first and second.studio.dir == "/b"
    write_config(cfg_path, studio={"dir": "/longer"})
    os.utime(cfg_path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))  # same mtime, other size
    assert load_config().studio.dir == "/longer"


def test_extra_ca_cert_reaches_the_model_layer(cfg_path, tmp_path):
    """`network.extra_ca_cert` is the CA `ai_models.tls.ca_cert` adds to certifi's roots; without it, None."""
    from ai_models import tls

    assert tls.ca_cert() is None
    ca = tmp_path / "ca.pem"
    ca.write_text("pem", encoding="utf-8")
    write_config(cfg_path, network={"extra_ca_cert": str(ca)})
    assert tls.ca_cert() == ca


def test_config_exits_with_the_message(tmp_path):
    """`config()` prints `Error: ` and the whole message on stderr and exits 1 for an invalid file. Run in a child
    process with its own config file."""
    cfg = write_config(tmp_path / "config.yaml", tasks={"chat": "o:m"})
    done = run_python("import plugin_settings\nplugin_settings.config()", child_env(SKILLS_CONFIG=str(cfg)))
    assert done.returncode == 1
    assert done.stderr == (f"Error: {cfg} is not valid:\n"
                           "  tasks.chat: provider 'o' is not in providers\n"
                           "The setup:settings skill describes every key and creates the file.\n")
