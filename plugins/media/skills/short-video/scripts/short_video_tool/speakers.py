"""Scenes with several voices.

A scene is split into runs of consecutive sentences with the same speaker and
the same resolved voice (`storyboard.sentence_voices`: the speaker's voice,
or the film's, with the sentence's own settings over it), so a change of
own settings starts a new run. A scene with one run is voiced as one script
(`sources/narration/<scene>/script.txt`); a scene with several runs gets one
part directory per run (`sources/narration/<scene>/p1/`, `p2/`, ...), each
voiced with the voiceover skill in its run's voice. `join` puts the parts
together into the one `narration.wav` and `timing.json` the rest of the
pipeline reads: each part is cut to its speech (first sentence start to last
sentence end), the first part keeps its lead silence, the last its tail, and
`voice.speaker_gap` seconds of silence go at each change of part.
"""

from __future__ import annotations

import itertools
import wave
from pathlib import Path

import numpy as np

from . import narration, storyboard


def runs(data: dict, scene: dict) -> list[tuple[str | None, dict, int, list[str]]]:
    """`(speaker, voice, first_index, sentences)` for each run of consecutive
    sentences with the same speaker and resolved voice (index 0-based; speaker
    None = no speaker, the film's voice). A scene without speakers or own
    voice settings is one run."""
    names = scene.get("speakers") or [None] * len(scene["narration"])
    voices = storyboard.sentence_voices(data, scene)
    out: list[tuple[str | None, dict, int, list[str]]] = []
    for i, (name, voice, text) in enumerate(zip(names, voices, scene["narration"])):
        if out and out[-1][:2] == (name, voice):
            out[-1][3].append(text)
        else:
            out.append((name, voice, i, [text]))
    return out


def part_dir(project: Path, scene_id: str, k: int) -> Path:
    """Directory of part `k` (1-based) of a scene with several runs."""
    return narration.script_dir(project, scene_id) / f"p{k}"


def part_dirs(scene_dir: Path) -> list[Path]:
    """The existing part directories `p<k>` under a scene's narration directory."""
    if not scene_dir.is_dir():
        return []
    return [d for d in scene_dir.iterdir() if d.is_dir() and d.name[:1] == "p" and d.name[1:].isdigit()]


def _label(speaker: str | None) -> str:
    return f"speaker {speaker!r}" if speaker else "the default voice (`voice:` in settings)"


def run_label(scene: dict, speaker: str | None, first: int) -> str:
    """How messages name a run: by its first sentence's own voice settings
    when it has them, else by its speaker."""
    if ((scene.get("voices") or [None] * (first + 1))[first]):
        return (f"speaker {speaker!r} with " if speaker else "") + f"sentence {first + 1}'s own voice settings"
    return _label(speaker)


def _style(v) -> str | None:
    """A style with whitespace collapsed; empty or missing is None."""
    return " ".join(str(v or "").split()) or None


def _voice_name(backend: str | None, name):
    """A chatterbox voice given as a file path, resolved (the shell may have
    expanded `~` or the agent passed a relative path); any other name as is."""
    s = str(name) if name is not None else None
    if backend == "chatterbox" and s and ("/" in s or s.startswith("~")):
        return str(Path(s).expanduser().resolve())
    return name


def check_voice(timing: dict, voice: dict, speaker: str | None, label: str | None = None) -> None:
    """Raise NarrationError unless `timing.json` was voiced with `voice`, the
    resolved voice (`backend`, `name`, `speed`, `style`) of `speaker`; the
    message starts with `label`, by default the speaker's. A null `name` is
    the backend's default as voiceover resolved it (the `speech` default
    depends on the configured provider), so any recorded voice matches it;
    `join` checks that parts with the same speaker and voice settings keep
    one voice."""
    label = label or _label(speaker)
    got = {"backend": timing.get("backend"), "voice": _voice_name(timing.get("backend"), timing.get("voice")),
           "speed": timing.get("speed"), "style": _style(timing.get("style"))}
    want = {"backend": voice.get("backend"), "voice": _voice_name(voice.get("backend"), voice.get("name")),
            "speed": voice.get("speed"), "style": _style(voice.get("style"))}
    if want["voice"] is None:
        if not got["voice"]:
            raise narration.NarrationError(f"{label}: timing.json records no voice; voice it again")
        want["voice"] = got["voice"]
    for key in ("backend", "voice", "style"):
        if got[key] != want[key]:
            raise narration.NarrationError(f"{label}: voiced with {key} {got[key]!r}, "
                                 f"the storyboard gives {want[key]!r}; voice it again")
    if not isinstance(got["speed"], (int, float)) or abs(float(got["speed"]) - float(want["speed"])) > 1e-6:
        raise narration.NarrationError(f"{label}: voiced with speed {got['speed']!r}, "
                             f"the storyboard gives {want['speed']!r}; voice it again")


def recorded_voices(timing: dict) -> list[dict]:
    """The voice each sentence of a stored `timing.json` was voiced with, as
    `check_voice` reads it: a joined recording's part voices (`speakers`),
    each repeated for its sentences, else the recording's own fields. A joined
    recording without the part sizes (made before they were recorded) has one
    part per run of `speaker` values."""
    sentences = timing.get("sentences") or []
    parts = timing.get("speakers")
    if not parts:
        return [timing] * len(sentences)
    sizes = [p.get("sentences") for p in parts]
    if None in sizes:
        sizes = [len(list(g)) for _, g in itertools.groupby(s.get("speaker") for s in sentences)]
    return [p for p, n in zip(parts, sizes) for _ in range(n)]


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Samples (int16) and sample rate of a mono 16-bit PCM WAV."""
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise narration.NarrationError(f"{path}: not mono 16-bit PCM")
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").copy(), w.getframerate()


def write_wav(path: Path, samples: np.ndarray, sr: int) -> Path:
    """Write int16 samples as mono 16-bit PCM WAV."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    return path


def _ms(t: float) -> float:
    return round(float(t), 3)


def join(parts: list[tuple[str | None, np.ndarray, int, dict]], gap: float,
         names: list[str | None] | None = None) -> tuple[np.ndarray, dict]:
    """Join voiced parts `(speaker, samples, sample_rate, timing)` into one
    recording and its `timing.json` dict (the voiceover format). Each part is
    cut from its first sentence start to its last sentence end, except the
    first part's lead and the last part's tail, which are kept; `gap` seconds
    of silence separate the parts. Sentence and word times are shifted,
    sentence indexes renumbered from 1, and each sentence gets `speaker`;
    `speakers` lists each part's speaker, voice and number of sentences.

    `names` is the voice name the storyboard gives each part (its resolved
    voice's `name`; None for every part when not given). A part with a name
    may use any voice name (`check_voice` compares it with the storyboard);
    parts with a null name (the backend's default) and the same speaker,
    backend, speed and style must share one voice."""
    if not parts:
        raise narration.NarrationError("no parts to join")
    rates = {sr for _, _, sr, _ in parts}
    if len(rates) != 1:
        raise narration.NarrationError(f"the parts have different sample rates: {', '.join(str(r) for r in sorted(rates))}")
    sr = rates.pop()
    resolved: dict[tuple, object] = {}
    for k, ((speaker, _, _, timing), name) in enumerate(zip(parts, names or [None] * len(parts))):
        if name is not None:
            continue
        key = (speaker, timing.get("backend"), timing.get("speed"), _style(timing.get("style")))
        v = resolved.setdefault(key, timing.get("voice"))
        if v != timing.get("voice"):
            raise narration.NarrationError(f"part {k + 1} ({_label(speaker)}) is voiced with voice "
                                           f"{timing.get('voice')!r}, an earlier part with {v!r}; voice it again")
    gap_n = int(round(gap * sr))
    last = len(parts) - 1
    chunks: list[np.ndarray] = []
    sentences: list[dict] = []
    voices: list[dict] = []
    pos = 0
    for k, (speaker, samples, _, timing) in enumerate(parts):
        sent = timing.get("sentences") or []
        if not sent:
            raise narration.NarrationError(f"part {k + 1} ({_label(speaker)}) has no sentences")
        cut0 = 0 if k == 0 else int(round(sent[0]["start"] * sr))
        cut1 = samples.size if k == last else int(round(sent[-1]["end"] * sr))
        if k > 0:
            chunks.append(np.zeros(gap_n, dtype=samples.dtype))
            pos += gap_n
        chunks.append(samples[cut0:cut1])
        shift = (pos - cut0) / sr
        pos += cut1 - cut0
        for s in sent:
            sentences.append({
                **s,
                "index": len(sentences) + 1,
                "start": _ms(s["start"] + shift),
                "end": _ms(s["end"] + shift),
                "words": [{**w, "start": _ms(w["start"] + shift), "end": _ms(w["end"] + shift)}
                          for w in s.get("words") or []],
                "speaker": speaker,
            })
        voices.append({"speaker": speaker, "backend": timing.get("backend"), "voice": timing.get("voice"),
                       "speed": timing.get("speed"), "style": timing.get("style"), "sentences": len(sent)})
    audio = np.concatenate(chunks)
    first = parts[0][3]
    out = {"audio": "narration.wav", "sample_rate": sr, "duration": _ms(audio.size / sr)}
    for key in ("backend", "model", "style", "voice", "speed"):
        if first.get(key) is not None:
            out[key] = first[key]
    out["speakers"] = voices
    out["sentences"] = sentences
    return audio, out
