"""Settings and paths for the voiceover CLI.

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the file. The one setting of the skill,
with the default used when unset:

    voiceover.voices_dir  reference recordings of `add-voice`, `<name>.<suffix>` each, and saved Fish voices,
                          `<name>.fish/` each (default <plugin data dir>/voiceover/voices)

The speech and align models, their providers, weights and default voices are in config.yaml (`tasks.speech`,
`tasks.align` and their providers). The model settings of an earlier version fail at load (`plugin_settings`).
"""

from __future__ import annotations

from pathlib import Path

from plugin_settings import Plugin, config, error  # noqa: F401 - re-exported

PLUGIN = Plugin.of(__file__)
plugin_data_dir = PLUGIN.data_dir
# The model names an earlier version took in place of a model id (as `--backend` and as a routes.md model); each is
# also the provider kind of its models now.
OLD_NAMES = ("kokoro", "chatterbox")
# Appended to a config error about a missing provider or model.
TEMPLATE_HINT = ("; the setup:settings template has a provider entry for each local speech kind (kokoro, chatterbox, "
                 "fish) and for the word aligner (kind torchaudio, `tasks.align`)")


def weights_dir() -> Path:
    """Where the local speech and align models keep their weights when their provider has no `dir`:
    `voiceover/` of the plugin data directory (where an earlier version downloaded them)."""
    return plugin_data_dir() / "voiceover"


def old_route_rows(path: Path) -> list[tuple[int, str]]:
    """(line number, name) of each routes.md row whose model is a name of `OLD_NAMES`."""
    if not path.is_file():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.lstrip().startswith("|") else []
        if len(cells) > 1 and cells[1] in OLD_NAMES:
            rows.append((n, cells[1]))
    return rows


def load_settings() -> None:
    """Load the settings (`Plugin.load`); exit when the file is not valid or a row of routes.md names a model by an
    earlier name (`OLD_NAMES`)."""
    from ai_models import routes

    PLUGIN.load()
    if rows := old_route_rows(routes.user_path()):
        n, name = rows[0]
        error(f"{routes.user_path()}:{n}: `{name}` is no longer a model; write the model id <provider>:<model> of a "
              f"provider of kind {name} in config.yaml (the setup:settings template has the provider entry and its "
              "model id)")


def voices_dir() -> Path:
    """Directory of the reference recordings, `<name>.<suffix>` each, and the saved Fish voices, `<name>.fish/`."""
    return config().voiceover.voices_dir or plugin_data_dir() / "voiceover" / "voices"
