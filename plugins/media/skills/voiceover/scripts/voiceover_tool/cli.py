"""Argparse dispatcher for `voiceover <command>`.

Commands:
    synth    Script (one sentence per line) -> narration.wav + timing.json.
    voices   List the voices of a speech model.
    setup    Download the weights of the speech and align models (synth does this on first use).
    add-voice  Store a reference recording as a voice (models that clone a voice).
    play     Open a media file in VLC.
    routes   Print the model routes of the speech task (`ai_models.routes`).
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
from ai_models import AIModelsError, routes

from . import config, voices
from .align import AlignFn, clip_aligner, sentence_words
from .assemble import DEFAULT_GAP, DEFAULT_LEAD, DEFAULT_TAIL, join, trim_silence, write_wav
from .script import read_script, split_style
from .speech import Narrator, TTSError
from .timing import SentenceTiming, build_timing, write_timing

WAV_NAME = "narration.wav"
TIMING_NAME = "timing.json"
# The tasks `routes` prints the rows of.
ROUTE_TASKS = ("speech",)
VOICE_NAME = "voice.wav"  # the first take of a `default` vllm-omni voice, with its transcript `voice.txt`

# (trimmed clip, sample rate) -> AlignFn for that clip
ClipAligner = Callable[[np.ndarray, int], AlignFn]


def synthesize_to_dir(
    narrator: Narrator,
    sentences: Sequence[str],
    out_dir: str | Path,
    *,
    voice: str,
    lead: float = DEFAULT_LEAD,
    gap: float = DEFAULT_GAP,
    tail: float = DEFAULT_TAIL,
    aligner: ClipAligner | None = None,
) -> tuple[Path, Path]:
    """Synthesize sentence by sentence, join, align, write WAV + timing.json.

    A `[style] sentence` line is spoken with its own style (`split_style`); every style is checked before the
    first request. With `aligner=None` only sentence times are written (`words` is empty and `aligned` is false).
    """
    if not sentences:
        raise ValueError("script has no sentences")
    styled = [split_style(s) for s in sentences]
    for style in dict.fromkeys(st for st, _ in styled if st):
        narrator.check_style(style)
    sentences = [text for _, text in styled]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sr = narrator.sample_rate
    clips = [trim_silence(narrator.synthesize(text, voice, style), sr) for style, text in styled]
    audio, spans = join(clips, sr, lead, gap, tail)

    timings: list[SentenceTiming] = []
    for i, (text, clip, (start, end)) in enumerate(zip(sentences, clips, spans), start=1):
        if aligner is None:
            words, aligned = [], False
        else:
            words, aligned = sentence_words(text, start, end, aligner(clip, sr), index=i)
        timings.append(SentenceTiming(i, text, start, end, aligned, words, styled[i - 1][0]))

    wav_path = write_wav(out_dir / WAV_NAME, audio, sr)
    timing = build_timing(
        audio=WAV_NAME,
        sample_rate=sr,
        duration=audio.size / sr,
        model=narrator.model,
        voice=voice,
        speed=narrator.speed,
        sentences=timings,
        style=narrator.style,
    )
    timing_path = write_timing(out_dir / TIMING_NAME, timing)
    if take := narrator.first_take():
        (out_dir / VOICE_NAME).write_bytes(take[0])
        (out_dir / VOICE_NAME).with_suffix(".txt").write_text(take[1] + "\n")
    return wav_path, timing_path


def _cmd_synth(args: argparse.Namespace) -> int:
    try:
        sentences = read_script(args.script)
    except OSError as e:
        config.error(f"cannot read script: {e}")
    if not sentences:
        config.error(f"{args.script}: no sentences (one sentence per line, blank lines skipped)")
    try:
        narrator = Narrator(args.model, style=args.style, speed=args.speed)
        aligner = None if args.no_align else clip_aligner()
        wav, timing = synthesize_to_dir(
            narrator,
            sentences,
            args.out_dir,
            voice=args.voice or narrator.default_voice,
            lead=args.lead,
            gap=args.gap,
            tail=args.tail,
            aligner=aligner,
        )
    except (ValueError, TTSError, AIModelsError) as e:
        config.error(str(e))
    print(wav)
    print(timing)
    return 0


def _cmd_voices(args: argparse.Namespace) -> int:
    try:
        narrator = Narrator(args.model)
        names = narrator.voices()
    except (ValueError, AIModelsError) as e:
        config.error(str(e))
    for v in names:
        print(f"{v}  (default)" if v == narrator.default_voice else v)
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    from ai_models import speech

    try:
        speech.fetch(args.model)
        clip_aligner()
    except AIModelsError as e:
        config.error(str(e))
    return 0


def _cmd_add_voice(args: argparse.Namespace) -> int:
    try:
        print(voices.add_voice(args.name, args.file, force=args.force, text=args.text))
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
    p.add_argument("--model", default=None,
                   help="Speech model id <provider>:<model> of the ai_models config (default: models.speech)")
    p.add_argument("--voice", default=None,
                   help="Voice name (default: the model's default voice); for a model that clones a voice also a "
                   "recording of add-voice or a path to one")
    p.add_argument("--speed", type=float, default=1.0, help="Pace, for models with a speed setting")
    p.add_argument("--style", default=None, help="Delivery instruction, e.g. 'calm documentary narrator', for "
                   "models that take instructions")
    p.add_argument("--lead", type=float, default=DEFAULT_LEAD, help=f"Silence before the first sentence, s (default {DEFAULT_LEAD})")
    p.add_argument("--gap", type=float, default=DEFAULT_GAP, help=f"Silence between sentences, s (default {DEFAULT_GAP})")
    p.add_argument("--tail", type=float, default=DEFAULT_TAIL, help=f"Silence after the last sentence, s (default {DEFAULT_TAIL})")
    p.add_argument("--no-align", action="store_true", help="Sentence times only, no word alignment")
    p.set_defaults(func=_cmd_synth)

    p = sub.add_parser("voices", help="List the voices of a speech model")
    p.add_argument("--model", default=None, help="Speech model id <provider>:<model> (default: models.speech)")
    p.set_defaults(func=_cmd_voices)

    p = sub.add_parser("setup", help="Download the weights of the speech and align models")
    p.add_argument("--model", default=None, help="Speech model id <provider>:<model> (default: models.speech)")
    p.set_defaults(func=_cmd_setup)

    p = sub.add_parser("add-voice", help="Store a reference recording as a voice (models that clone a voice: "
                                         "chatterbox, vllm-omni)")
    p.add_argument("name", help="Voice name, e.g. alice")
    p.add_argument("file", help="Recording of the speaker, longer than 5 s (10-20 s of clean speech)")
    p.add_argument("--force", action="store_true", help="Replace an existing voice of that name")
    p.add_argument("--text", default=None,
                   help="Transcript of the recording; needed to use the voice with a vllm-omni speech model")
    p.set_defaults(func=_cmd_add_voice)

    p = sub.add_parser("play", help="Open a media file in VLC")
    p.add_argument("file")
    p.set_defaults(func=_cmd_play)

    routes.command(sub, ROUTE_TASKS)
    return parser


def main(argv: list[str] | None = None) -> None:
    config.load_settings()
    args = build_parser().parse_args(argv)
    sys.exit(args.func(args))
