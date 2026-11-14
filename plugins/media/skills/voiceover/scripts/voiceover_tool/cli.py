"""Argparse dispatcher for `voiceover <command>`.

Commands:
    synth    Script (one sentence per line) -> narration.wav + timing.json.
    voices   List the voices of a backend.
    setup    Download all model weights (synth does this on first use).
    add-voice  Store a reference recording as a chatterbox voice.
    play     Open a media file in VLC.
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from . import config, download
from .align import AlignFn, sentence_words
from .assemble import DEFAULT_GAP, DEFAULT_LEAD, DEFAULT_TAIL, join, trim_silence, write_wav
from .backends import BACKENDS, DEFAULT_BACKEND, TTSBackend, get_backend
from .speech import TTSError
from .script import read_script
from .timing import SentenceTiming, build_timing, write_timing

WAV_NAME = "narration.wav"
TIMING_NAME = "timing.json"

# (trimmed clip, sample rate) -> AlignFn for that clip
ClipAligner = Callable[[np.ndarray, int], AlignFn]


def synthesize_to_dir(
    backend: TTSBackend,
    sentences: Sequence[str],
    out_dir: str | Path,
    *,
    voice: str,
    speed: float = 1.0,
    lead: float = DEFAULT_LEAD,
    gap: float = DEFAULT_GAP,
    tail: float = DEFAULT_TAIL,
    aligner: ClipAligner | None = None,
) -> tuple[Path, Path]:
    """Synthesize sentence by sentence, join, align, write WAV + timing.json.

    With `aligner=None` only sentence times are written (`words` is empty and
    `aligned` is false).
    """
    if not sentences:
        raise ValueError("script has no sentences")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sr = backend.sample_rate
    clips = [trim_silence(backend.synthesize(s, voice, speed), sr) for s in sentences]
    audio, spans = join(clips, sr, lead, gap, tail)

    timings: list[SentenceTiming] = []
    for i, (text, clip, (start, end)) in enumerate(zip(sentences, clips, spans), start=1):
        if aligner is None:
            words, aligned = [], False
        else:
            words, aligned = sentence_words(text, start, end, aligner(clip, sr), index=i)
        timings.append(SentenceTiming(i, text, start, end, aligned, words))

    wav_path = write_wav(out_dir / WAV_NAME, audio, sr)
    timing = build_timing(
        audio=WAV_NAME,
        sample_rate=sr,
        duration=audio.size / sr,
        backend=backend.name,
        voice=voice,
        speed=speed,
        sentences=timings,
        model=getattr(backend, "model", None),
        style=getattr(backend, "style", None),
    )
    timing_path = write_timing(out_dir / TIMING_NAME, timing)
    return wav_path, timing_path


def setup(include_kokoro: bool = True, include_aligner: bool = True, include_chatterbox: bool = False) -> list[Path]:
    """Download the weights that are missing; return their paths."""
    weights = list(download.kokoro_weights()) if include_kokoro else []
    if include_aligner:
        weights.append(download.aligner_weight())
    if include_chatterbox:
        weights.extend(download.chatterbox_weights())
    return [download.ensure_weight(w) for w in weights]


def _cmd_synth(args: argparse.Namespace) -> int:
    from .align import MMSAligner

    try:
        sentences = read_script(args.script)
    except OSError as e:
        config.error(f"cannot read script: {e}")
    if not sentences:
        config.error(f"{args.script}: no sentences (one sentence per line, blank lines skipped)")
    try:
        backend = get_backend(args.backend, style=args.style)
    except ValueError as e:
        config.error(str(e))

    try:
        setup(
            include_kokoro=backend.name == "kokoro",
            include_aligner=not args.no_align,
            include_chatterbox=backend.name == "chatterbox",
        )
    except download.DownloadError as e:
        config.error(str(e))
    aligner = None
    if not args.no_align:
        aligner = MMSAligner(config.aligner(), download.weight_path(download.aligner_weight()).parent).for_clip
    try:
        wav, timing = synthesize_to_dir(
            backend,
            sentences,
            args.out_dir,
            voice=args.voice or backend.default_voice,
            speed=args.speed,
            lead=args.lead,
            gap=args.gap,
            tail=args.tail,
            aligner=aligner,
        )
    except (ValueError, TTSError) as e:
        config.error(str(e))
    print(wav)
    print(timing)
    return 0


def _cmd_voices(args: argparse.Namespace) -> int:
    try:
        backend = get_backend(args.backend)
    except ValueError as e:
        config.error(str(e))
    try:
        voices = backend.voices()
    except download.DownloadError as e:
        config.error(str(e))
    for v in voices:
        print(f"{v}  (default)" if v == backend.default_voice else v)
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    try:
        paths = setup(include_chatterbox=args.chatterbox)
    except download.DownloadError as e:
        config.error(str(e))
    for p in paths:
        print(p)
    return 0


VOICE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def add_voice(name: str, src: str | Path, force: bool = False) -> Path:
    """Copy a reference recording to `<voices dir>/<name><suffix>`."""
    from .chatterbox import AUDIO_SUFFIXES, BUILTIN_VOICE, MIN_REFERENCE_SECONDS

    if not VOICE_NAME_RE.match(name) or name == BUILTIN_VOICE:
        raise ValueError(f"voice name {name!r}: use lowercase letters, digits, '-' and '_' (not {BUILTIN_VOICE!r})")
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


def _cmd_add_voice(args: argparse.Namespace) -> int:
    try:
        print(add_voice(args.name, args.file, force=args.force))
    except (ValueError, OSError, RuntimeError) as e:
        config.error(str(e))
    return 0


def play_command(path: Path, system: str | None = None) -> list[str]:
    """The command for `play` under the OS `system` (`platform.system()`, default this one): `open -a VLC`
    on macOS, else `xdg-open`, which opens the file in the desktop's default application."""
    if (system or platform.system()) == "Darwin":
        return ["open", "-a", "VLC", str(path)]
    return ["xdg-open", str(path)]


def _cmd_play(args: argparse.Namespace) -> int:
    p = Path(args.file).expanduser()
    if not p.exists():
        config.error(f"not found: {p}")
    return subprocess.run(play_command(p)).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voiceover", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("synth", help="Script -> narration.wav + timing.json")
    p.add_argument("--script", required=True, help="Text file, one sentence per line")
    p.add_argument("--out-dir", required=True, help="Directory for narration.wav and timing.json")
    p.add_argument("--backend", default=DEFAULT_BACKEND, choices=sorted(BACKENDS))
    p.add_argument(
        "--voice",
        default=None,
        help="Voice name (default: the backend's voice setting, VOICEOVER_KOKORO_VOICE, "
        "VOICEOVER_CHATTERBOX_VOICE or VOICEOVER_SPEECH_VOICE); "
        "for chatterbox also a path to a reference recording",
    )
    p.add_argument("--speed", type=float, default=1.0,
                   help="kokoro, and speech with an OpenAI-style model (not Gemini TTS)")
    p.add_argument("--style", default=None, help="Delivery instruction, e.g. 'calm documentary narrator' "
                   "(speech only)")
    p.add_argument("--lead", type=float, default=DEFAULT_LEAD, help=f"Silence before the first sentence, s (default {DEFAULT_LEAD})")
    p.add_argument("--gap", type=float, default=DEFAULT_GAP, help=f"Silence between sentences, s (default {DEFAULT_GAP})")
    p.add_argument("--tail", type=float, default=DEFAULT_TAIL, help=f"Silence after the last sentence, s (default {DEFAULT_TAIL})")
    p.add_argument("--no-align", action="store_true", help="Sentence times only, no word alignment")
    p.set_defaults(func=_cmd_synth)

    p = sub.add_parser("voices", help="List voices")
    p.add_argument("--backend", default=DEFAULT_BACKEND, choices=sorted(BACKENDS))
    p.set_defaults(func=_cmd_voices)

    p = sub.add_parser("setup", help="Download all model weights")
    p.add_argument("--chatterbox", action="store_true", help="Also download the Chatterbox weights (about 3 GB)")
    p.set_defaults(func=_cmd_setup)

    p = sub.add_parser("add-voice", help="Store a reference recording as a chatterbox voice")
    p.add_argument("name", help="Voice name, e.g. alice")
    p.add_argument("file", help="Recording of the speaker, longer than 5 s (10-20 s of clean speech)")
    p.add_argument("--force", action="store_true", help="Replace an existing voice of that name")
    p.set_defaults(func=_cmd_add_voice)

    p = sub.add_parser("play", help="Open a media file in VLC")
    p.add_argument("file")
    p.set_defaults(func=_cmd_play)
    return parser


def main(argv: list[str] | None = None) -> None:
    config.load_settings()
    args = build_parser().parse_args(argv)
    sys.exit(args.func(args))
