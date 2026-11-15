"""A failed weight download of `setup` is one error line naming the URL."""

from tests.settings_env import write_config

from .cli_run import voiceover

UNREACHABLE = "http://127.0.0.1:1/model.bin"


def test_setup_failure_is_one_error_line(tmp_path):
    """The Kokoro model's files are at a closed local port, so the download fails without reaching the network."""
    config = write_config(tmp_path / "config.yaml",
                          providers={"k": {"kind": "kokoro", "model_url": UNREACHABLE, "voices_url": UNREACHABLE,
                                           "langs": {"af_": "en-us"}, "dir": str(tmp_path / "w")}},
                          models={"speech": "k:kokoro-v1.0"})
    p = voiceover("setup", SKILLS_CONFIG=str(config))
    assert p.returncode == 1, p.stderr
    assert "Traceback" not in p.stderr
    assert f"Error: cannot download {UNREACHABLE}" in p.stderr
