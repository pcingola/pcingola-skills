"""Unit tests for plugin_settings.ca: the extra CA from the settings EXTRA_CA_CERT or NODE_EXTRA_CA_CERTS.
Each case runs in a child process with a config file of its own (SKILLS_CONFIG)."""
from tests.settings_env import write_config
from tests.subproc import child_env, py_value

IMPORT = "from plugin_settings import ca"


def cert(tmp_path, settings: dict[str, str], keys: str = "") -> object:
    cfg = write_config(tmp_path / "config.yaml", settings)
    return py_value(IMPORT, f"ca.ca_cert({keys})", child_env({"HOME": str(tmp_path), "SKILLS_CONFIG": str(cfg)}))


def test_first_existing_setting_wins(tmp_path):
    """ca.ca_cert returns the first setting that names an existing file, skipping one whose file is
    missing. Guards the precedence of EXTRA_CA_CERT over NODE_EXTRA_CA_CERTS."""
    a, b = tmp_path / "a.pem", tmp_path / "b.pem"
    a.write_text("x")
    b.write_text("x")
    assert cert(tmp_path, {"EXTRA_CA_CERT": str(a), "NODE_EXTRA_CA_CERTS": str(b)}) == str(a)
    assert cert(tmp_path, {"EXTRA_CA_CERT": str(tmp_path / "missing.pem"), "NODE_EXTRA_CA_CERTS": str(b)}) == str(b)


def test_custom_keys(tmp_path):
    """ca.ca_cert reads the keys the caller passes. Guards the keys parameter."""
    a = tmp_path / "a.pem"
    a.write_text("x")
    assert cert(tmp_path, {"OTHER_CA": str(a)}, "('OTHER_CA',)") == str(a)


def test_none_when_nothing_set(tmp_path):
    """ca.ca_cert returns None when no setting names an existing file. Guards callers against loading a
    missing CA file, and the default trust when no extra CA is set."""
    assert cert(tmp_path, {}) is None
    assert cert(tmp_path, {"EXTRA_CA_CERT": "/nonexistent.pem"}) is None
