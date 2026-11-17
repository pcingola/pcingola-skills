"""The narrator: a speech model of the `ai_models` config (`--model`, else `tasks.speech`), one request per
sentence through `ai_models.speech.speak`.

`ai_models.speech.check` refuses a speed or a style the model does not take when the narrator is made, before
any request or model load. The style goes as the model's instructions. The default voice is the model's
(`ai_models` provider `voice`, else its kind's). A model whose kind clones a voice (chatterbox) also takes a
reference recording of `add-voice` (`voices.py`), passed as its path; `voices` lists those after the model's own
voices. The answer is a WAV file, resampled to 24 kHz when it has another rate (Drama 3: 44.1 kHz); raw 16-bit PCM
(some OpenAI-compatible servers) is taken as 24 kHz.

A fish model (Fish Audio Drama 3) keeps the first take of each speaker as the reference of the rest, so one command
has one voice per speaker; `synth` writes each as `voice.wav` (`voice-<speaker>.wav`) + `.txt`. A voice name other
than `default` given to a fish model (`--voice`, `--speaker`) is a saved Fish voice (`voices.fish_folder`): when it
exists, its take seeds `fish.takes` before the first request, so later commands keep the voice; when it does not,
the first take of its speaker is saved under that name after synthesis (`save_voices`).
"""

from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import numpy as np

from . import config, voices
from .script import NAME_RE, Line

SAMPLE_RATE = 24_000


class TTSError(Exception):
    """A TTS request failed or returned unusable audio."""


def pcm16_to_float(data: bytes) -> np.ndarray:
    """Little-endian signed 16-bit PCM -> float32 in [-1, 1)."""
    if len(data) % 2:
        data = data[:-1]
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def decode(data: bytes) -> tuple[np.ndarray, int]:
    """Mono float32 samples and the sample rate of a 16-bit WAV file, or of raw 16-bit PCM at 24 kHz."""
    if data[:4] != b"RIFF":
        return pcm16_to_float(data), SAMPLE_RATE
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2:
            raise TTSError(f"expected 16-bit audio, got {8 * w.getsampwidth()}-bit")
        samples = pcm16_to_float(w.readframes(w.getnframes()))
        return samples.reshape(-1, w.getnchannels()).mean(axis=1), w.getframerate()


def resample(samples: np.ndarray, rate: int, target: int) -> np.ndarray:
    """`samples` at `rate` Hz resampled to `target` Hz (torchaudio's band-limited sinc interpolation)."""
    import torch
    import torchaudio.functional as F

    return F.resample(torch.from_numpy(np.ascontiguousarray(samples)), rate, target).numpy()


class Narrator:
    """Speech model `model` (else `tasks.speech`) with `style`, `speed`, the voice of each named speaker
    (`speakers`, a name of `@name` lines to a voice) and more request fields (`params`); `ValueError` when the config
    names no such model or the model does not take the style, speed, speakers or parameters. Local weights live in
    `config.weights_dir()` unless the provider sets `dir`."""

    sample_rate = SAMPLE_RATE

    def __init__(self, model: str | None = None, style: str | None = None, speed: float = 1.0,
                 speakers: dict[str, str] | None = None, params: dict | None = None) -> None:
        from ai_models import AIModelsError, ConfigError
        from ai_models import fish, speech

        try:
            m = speech.check(model, speed=speed, instructions=style, params=params, weights_dir=config.weights_dir())
        except ConfigError as e:
            raise ValueError(f"{e}{config.TEMPLATE_HINT}") from None
        except AIModelsError as e:
            raise ValueError(str(e)) from None
        self.model, self.kind, self.default_voice = m.id, m.kind, m.default_voice
        self.clones, self.instructions, self.tags = m.traits.clones, m.instructions, m.traits.tags
        self.one_voice = m.traits.one_voice
        speakers = dict(speakers or {})
        if speakers and not self.tags:
            raise ValueError(f"{m.id} takes no speakers (`@speaker` lines are for a model that takes inline tags)")
        if bad := [n for n in speakers if not NAME_RE.match(n)]:
            raise ValueError(f"--speaker {bad[0]!r}: a speaker name has lowercase letters, digits, '-' and '_'")
        self.style, self.speed, self.speakers, self.params = style, speed, speakers, dict(params or {})
        self.made_up: list[str] = []  # the speakers of `@name` lines without a voice, in order of first line
        self.resolved: dict[str | None, str] = {}  # speaker (None: the narrator) -> the voice sent (a path or name)
        self.fish_voices: dict[str | None, Path] = {}  # speaker -> the folder of its saved Fish voice (fish models)
        self.fish = m.kind == fish.KIND

    def lines(self, sentences: list[str]) -> list[Line]:
        """Each script line as the model takes it (`Line.of`): speakers and inline tags for a model that takes tags,
        a leading `[style]` for one that takes styles, else literal text; `ValueError` for a line the model would
        not take."""
        return [Line.of(s, styles=self.instructions, tags=self.tags, model=self.model) for s in sentences]

    def _reference(self, voice: str, speaker: str | None) -> str:
        """`voice` of `speaker` as sent: a cloning model's recording path, a fish model's default voice (a named Fish
        voice goes to `fish_voices`), else `voice`; `ValueError` when the recording is missing, for a recording given
        to a fish model, or for a voice other than the default of a model that has only that one."""
        if self.fish:
            if (folder := voices.fish_folder(voice)) is not None:
                self.fish_voices[speaker] = folder
            return self.default_voice
        if self.one_voice and voice != self.default_voice:
            raise ValueError(f"{self.model} has only the voice {self.default_voice!r}; a model of kind chatterbox "
                             "clones a recorded voice")
        if not self.clones or voice == voices.DEFAULT_VOICE:
            return voice
        return str(voices.reference_path(voice))

    def prepare(self, lines: list[Line], voice: str) -> None:
        """Resolve every voice before the first request: the narrator's `voice` and each speaker's (`--speaker`, else
        a made-up voice, `default`). `ValueError` for a `--speaker` no line uses, or a recording that is missing. The made-up speakers are named on stderr."""
        used = list(dict.fromkeys(line.speaker for line in lines if line.speaker))
        if unused := [n for n in self.speakers if n not in used]:
            raise ValueError(f"--speaker {', '.join(unused)}: no `@name` line of the script has that speaker "
                             f"(speakers in the script: {', '.join(used) or 'none'})")
        self.fish_voices = {}
        self.resolved = {None: self._reference(voice, None)}
        for name in used:
            self.resolved[name] = self._reference(self.speakers.get(name, voices.DEFAULT_VOICE), name)
        self._seed_fish_voices()
        self.made_up = [n for n in used if n not in self.speakers]
        if self.made_up:
            print(f"voiceover: made-up voices (the first line of each is the reference of the rest): "
                  f"{', '.join(self.made_up)}", file=sys.stderr)

    def _seed_fish_voices(self) -> None:
        """Seed `fish.takes` with the saved take of each speaker whose Fish voice exists, so every request of that
        speaker has it as reference; `ValueError` for a folder that holds no saved take."""
        from ai_models import AIModelsError, fish
        from ai_models.fish_take import Take

        for speaker, folder in self.fish_voices.items():
            if folder.is_dir():
                try:
                    fish.takes.keep(self.model, speaker, Take.load(folder))
                except AIModelsError as e:
                    raise ValueError(str(e)) from None

    def save_voices(self) -> list[Path]:
        """Save the first take of each speaker whose named Fish voice did not exist (`Take.save`); the folders
        written. A name two speakers share is saved from the first speaker that has a take."""
        from ai_models import fish

        saved = []
        for speaker, folder in self.fish_voices.items():
            if not folder.exists() and (take := fish.takes.get(self.model, speaker)) is not None:
                saved.append(take.save(folder))
        return saved

    def voices(self) -> list[str]:
        """The model's voices, then the reference recordings when the model clones a voice, or the saved Fish voices
        for a fish model."""
        from ai_models import speech

        own = speech.voices(self.model, config.weights_dir())
        extra = voices.names() if self.clones else voices.fish_names() if self.fish else []
        return own + [v for v in extra if v not in own]

    def first_takes(self) -> dict[str | None, tuple[bytes, str]]:
        """Per speaker (None: the narrator), (WAV, text) of its first take of a fish model in this process; empty for
        other kinds."""
        from ai_models import fish

        if not self.fish:
            return {}
        return {s: (t.wav, t.text) for s in (None, *self.made_up) if (t := fish.takes.get(self.model, s))}

    def synthesize(self, line: Line) -> np.ndarray:
        """Mono float32 samples of `line` at `sample_rate`, in its speaker's resolved voice (`prepare`), with its own
        style (else the narrator's)."""
        from ai_models import AIModelsError, speech

        try:
            data = speech.speak(line.said, voice=self.resolved[line.speaker], model=self.model,
                                instructions=line.style or self.style, speed=self.speed, speaker=line.speaker,
                                params=self.params or None, weights_dir=config.weights_dir())
        except AIModelsError as e:
            msg = str(e)
            raise TTSError(msg if msg.startswith(self.model) else f"{self.model}: {msg}") from None
        except Exception as e:
            if getattr(e, "status_code", None) is None:
                raise
            raise TTSError(f"{self.model}: {e}") from None  # the provider refused the request (a voice it lacks)
        samples, rate = decode(data)
        if rate != self.sample_rate:
            samples = resample(samples, rate, self.sample_rate)
        if not samples.size:
            raise TTSError(f"{self.model} returned no audio for: {line.said[:80]!r}")
        return samples
