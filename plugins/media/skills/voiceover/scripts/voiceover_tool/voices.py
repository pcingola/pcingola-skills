"""Reference recordings for the speech models that clone a voice (provider kind chatterbox).

A voice is `<name>.<suffix>` in `config.voices_dir()`, or a path to a recording. `default` is the model's own voice.
A recording must be longer than `MIN_REFERENCE_SECONDS`.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import config

DEFAULT_VOICE = "default"
MIN_REFERENCE_SECONDS = 5.0
AUDIO_SUFFIXES = (".wav", ".flac", ".mp3", ".m4a")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def names() -> list[str]:
    """The name of every recording in the voices directory."""
    d = config.voices_dir()
    return sorted(p.stem for p in d.iterdir() if p.suffix.lower() in AUDIO_SUFFIXES) if d.is_dir() else []


def reference_path(voice: str) -> Path | None:
    """The recording of `voice` (a name in the voices directory or a path), None for `default`."""
    if voice == DEFAULT_VOICE:
        return None
    p = Path(voice).expanduser()
    if p.suffix.lower() in AUDIO_SUFFIXES and p.is_file():
        return p
    d = config.voices_dir()
    for suffix in AUDIO_SUFFIXES:
        p = d / f"{voice}{suffix}"
        if p.is_file():
            return p
    raise ValueError(f"unknown voice {voice!r}: no {voice}.wav in {d}; add one with `voiceover.sh add-voice NAME FILE`")


def add_voice(name: str, src: str | Path, force: bool = False) -> Path:
    """Copy a reference recording to `<voices dir>/<name><suffix>`."""
    if not NAME_RE.match(name) or name == DEFAULT_VOICE:
        raise ValueError(f"voice name {name!r}: use lowercase letters, digits, '-' and '_' (not {DEFAULT_VOICE!r})")
    src = Path(src).expanduser()
    if src.suffix.lower() not in AUDIO_SUFFIXES:
        raise ValueError(f"{src}: expected one of {', '.join(AUDIO_SUFFIXES)}")
    import soundfile as sf

    duration = sf.info(str(src)).duration
    if duration <= MIN_REFERENCE_SECONDS:
        raise ValueError(f"{src}: {duration:.1f} s; a reference must be longer than {MIN_REFERENCE_SECONDS:g} s")
    d = config.voices_dir()
    existing = [p for p in d.glob(f"{name}.*") if p.suffix.lower() in AUDIO_SUFFIXES] if d.is_dir() else []
    if existing and not force:
        raise ValueError(f"voice {name!r} exists ({existing[0]}); pass --force to replace it")
    d.mkdir(parents=True, exist_ok=True)
    for p in existing:
        p.unlink()
    dest = d / f"{name}{src.suffix.lower()}"
    shutil.copyfile(src, dest)
    return dest
