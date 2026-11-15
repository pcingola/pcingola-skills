"""Argparse dispatcher for `music <command>`.

Commands:
    generate   Prompt (plus the inputs the model takes) -> audio file(s) of the
               `music` model (or --model) of the `ai_models` config, with
               `<out>.json` (model, exact prompt sent, options, MIME type,
               finish reason, duration, the crest factor check of `crest.py` for a model with
               `min_crest_db`) and `<out>.txt` (the text the model returns, when it returns any).
    fit        Loop or trim a track to an exact length, with fades.
    analyze    Per-clip reports on how clips fit their briefs: a model
               description, signal measurements and images (`analyze.py`).
    routes     Print the model routes of the music and audio tasks (`ai_models.routes`).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from ai_models import routes

from . import config, crest, fit, prompt

EXTENSIONS = (".mp3", ".wav")
# Seeds drawn when --seed is not given are below this (torch.Generator takes 64-bit seeds).
MAX_SEED = 2**31
IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def sample_paths(out: Path, n: int) -> list[Path]:
    """`out` for one sample; `<stem>_1<ext>` ... `<stem>_N<ext>` for several."""
    if n <= 1:
        return [out]
    return [out.with_name(f"{out.stem}_{i}{out.suffix}") for i in range(1, n + 1)]


def image_mime(path: str) -> str:
    """The MIME type of a PNG, JPEG or WebP path; exits for another suffix."""
    mime = IMAGE_MIME.get(Path(path).suffix.lower())
    if mime is None:
        config.error(f"--image {path}: use PNG, JPEG or WebP")
    return mime


def sidecar(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt and args.prompt_file:
        config.error("give the prompt as an argument or --prompt-file, not both")
    if args.prompt_file:
        try:
            return Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except OSError as e:
            config.error(f"--prompt-file: {e}")
    if not args.prompt:
        config.error("no prompt: give it as an argument or with --prompt-file")
    return args.prompt.strip()


def _check(args: argparse.Namespace) -> None:
    if args.lyrics and args.instrumental:
        config.error("--lyrics and --instrumental are mutually exclusive")
    if args.bpm is not None and args.bpm <= 0:
        config.error("--bpm must be positive")
    if args.seconds is not None and args.seconds <= 0:
        config.error("--seconds must be positive")
    if args.seed is not None and args.samples is not None:
        config.error("--seed and --samples are mutually exclusive")
    if args.samples is not None and args.samples < 1:
        config.error("--samples must be at least 1")


def audio_ext(audio: bytes) -> str:
    """`.wav` for a RIFF file, else `.mp3`."""
    return ".wav" if audio[:4] == b"RIFF" else ".mp3"


def output_path(target: Path, audio: bytes, local: bool) -> Path:
    """The path written for `audio` asked at `target`: `target` when the format matches or a local model's
    WAV is encoded to the asked MP3, else `target` with the suffix of the returned format."""
    path = target.with_suffix(audio_ext(audio))
    if path != target and local and target.suffix.lower() == ".mp3":
        return target
    return path


def existing_outputs(paths: list[Path]) -> list[Path]:
    """The files among `paths` and their `.json` and `.txt` sidecars that exist."""
    return [f for p in paths for f in (p, sidecar(p, ".json"), sidecar(p, ".txt")) if f.exists()]


def _refuse_overwrite(paths: list[Path], force: bool) -> None:
    existing = existing_outputs(paths)
    if existing and not force:
        config.error(f"{existing[0]} exists; pass --force to overwrite")


def _cmd_generate(args: argparse.Namespace) -> int:
    from ai_models import config as ai_config
    from ai_models import music
    from ai_models.errors import AIModelsError
    from ai_models.models import kind

    from .measure import MeasureError

    _check(args)
    text = _read_prompt(args)
    out = Path(args.out).expanduser()
    if out.suffix.lower() not in EXTENSIONS:
        config.error(f"--out must end in {' or '.join(EXTENSIONS)}, got {out.name}")
    _refuse_overwrite(sample_paths(out, args.samples or 1), args.force)
    try:
        images = [(Path(p).read_bytes(), image_mime(p)) for p in args.image or []]
    except OSError as e:
        config.error(f"--image: {e}")
    lyrics = None
    if args.lyrics:
        try:
            lyrics = Path(args.lyrics).read_text(encoding="utf-8")
        except OSError as e:
            config.error(f"--lyrics: {e}")
    try:
        model_id = ai_config.resolve(args.model, "music")
        local = kind(model_id) == "diffusers"
    except AIModelsError as e:
        config.error(str(e))
    sent, sent_lyrics = prompt.request(text, lyrics, args.instrumental, args.bpm, local)

    def compose(seed: int | None) -> list:
        return music.compose(sent, seconds=args.seconds, lyrics=sent_lyrics, seed=seed, negative=args.negative,
                             images=images, samples=args.samples, model=model_id)

    threshold, records, kept = None, [], {}
    try:
        threshold = music.min_crest_db(model_id)
        if threshold is None:
            tracks = compose(args.seed)
        else:
            attempts, seed = crest.attempts_setting(), args.seed
            if seed is None and not args.samples and "seed" in music.takes(model_id):
                seed = random.randrange(MAX_SEED - attempts)
            tracks, records = crest.regenerate(compose, threshold, attempts, seed)
            kept = next(r for r in records if r["kept"])
            if min(kept["crest_db"]) < threshold:
                config.warn(f"all {len(records)} requests gave a track with a crest factor below {threshold:g} dB "
                            f"(loud, compressed); kept the request at {min(kept['crest_db']):g} dB")
    except AIModelsError as e:
        config.error(str(e) if model_id in str(e) else f"{model_id}: {e}")
    except MeasureError as e:
        config.error(f"crest factor: {e}")

    options = {"image": args.image, "lyrics": args.lyrics, "instrumental": args.instrumental, "bpm": args.bpm,
               "seconds": args.seconds, "negative": args.negative, "seed": args.seed, "samples": args.samples}
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    targets = sample_paths(out, len(tracks))
    _refuse_overwrite([output_path(t, track.audio, local) for t, track in zip(targets, tracks)], args.force)
    for i, (target, track) in enumerate(zip(targets, tracks), 1):
        path = target.with_suffix(audio_ext(track.audio))
        path.parent.mkdir(parents=True, exist_ok=True)
        if output_path(target, track.audio, local) == target and path != target:
            try:
                fit.encode(track.audio, target)
            except fit.FitError as e:
                config.error(str(e))
            path = target
        else:
            if path != target:
                config.warn(f"{model_id} returned {path.suffix[1:].upper()} audio; writing {path.name}")
            path.write_bytes(track.audio)
        if track.text:
            sidecar(path, ".txt").write_text(track.text + "\n", encoding="utf-8")
        meta = {
            "model": model_id,
            "prompt": sent,
            **({"lyrics": lyrics} if lyrics else {}),
            "options": {k: v for k, v in options.items() if v is not None and v is not False and v != []},
            "mime_type": "audio/wav" if path.suffix == ".wav" else "audio/mpeg",
            "finish_reason": track.finish_reason,
            "duration": fit.duration(path),
            "created_at": created,
            **({"sample": i} if len(tracks) > 1 else {}),
            **({"crest": {"crest_db": kept["crest_db"][i - 1], "min_crest_db": threshold,
                          "below_threshold": kept["crest_db"][i - 1] < threshold, "attempts": records}}
               if records else {}),
        }
        sidecar(path, ".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(path)
    return 0


def _cmd_fit(args: argparse.Namespace) -> int:
    try:
        out = fit.fit(Path(args.input).expanduser(), Path(args.out).expanduser(), args.seconds,
                      args.fade_in, args.fade_out)
    except fit.FitError as e:
        config.error(str(e))
    print(out)
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    from .analyze import AnalyzeError, run

    if args.jobs < 1:
        config.error("--jobs must be at least 1")
    try:
        return run(args.inputs, args.brief, args.prompts, args.only, args.model, args.out_dir, args.jobs)
    except AnalyzeError as e:
        config.error(str(e))


# generate takes the `music` model, analyze the `audio` model; `routes` prints their rows.
ROUTE_TASKS = ("music", "audio")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="music", description="Music generation with the music model of the "
                                                          "ai_models config (a Google music model or a local diffusers model).")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("generate", help="Generate music from a prompt")
    c.add_argument("prompt", nargs="?", help="Text prompt (or --prompt-file)")
    c.add_argument("--prompt-file", help="Read the prompt from a file")
    c.add_argument("-o", "--out", required=True,
                   help="Output audio, .mp3 or .wav; the suffix follows the format the model returns "
                        "(remote models return MP3 or WAV; local models: WAV, or MP3 through FFmpeg)")
    c.add_argument("--model", help="Model id <provider>:<model> of the ai_models config (default: its music model)")
    c.add_argument("--image", action="append", metavar="PATH",
                   help="Reference image, PNG, JPEG or WebP, repeatable up to 10 (models that take images)")
    c.add_argument("--lyrics", metavar="FILE", help="Sung lyrics with [Verse]/[Chorus] tags (models that sing)")
    c.add_argument("--instrumental", action="store_true", help="No vocals (models that sing)")
    c.add_argument("--bpm", type=int, help="Tempo in beats per minute (written into the prompt)")
    c.add_argument("--seconds", type=int, help="Requested length (models that take a length; exact for local models)")
    c.add_argument("--negative", help="What to leave out (models with a negative prompt)")
    c.add_argument("--seed", type=int, help="Seed for repeatable output (models that take a seed, local models); the "
                                                       "first seed of the crest factor attempts")
    c.add_argument("--samples", type=int,
                   help="Number of tracks, files <stem>_1 ... <stem>_N (models that return several samples; not with --seed)")
    c.add_argument("--force", action="store_true", help="Overwrite existing output")
    c.set_defaults(func=_cmd_generate)

    c = sub.add_parser("fit", help="Loop or trim a track to an exact length")
    c.add_argument("input")
    c.add_argument("-o", "--out", required=True, help="Output (.mp3, .wav or .m4a)")
    c.add_argument("--seconds", type=float, required=True, help="Target length")
    c.add_argument("--fade-in", type=float, default=0.0, help="Fade-in seconds (default 0)")
    c.add_argument("--fade-out", type=float, default=2.0, help="Fade-out seconds (default 2)")
    c.set_defaults(func=_cmd_fit)

    c = sub.add_parser("analyze", help="Check clips against their briefs: model description, measurements, images")
    c.add_argument("inputs", nargs="+", metavar="FILE_OR_DIR", help="Audio files and folders of audio files")
    c.add_argument("--brief", help="Style brief every clip should match")
    c.add_argument("--prompts", metavar="FILE", help="File mapping file names to the prompt each clip was made from")
    c.add_argument("--only", action="append", choices=["model", "signal", "images"],
                   help="Run only this analysis (repeatable; default: all three)")
    c.add_argument("--model", help="Chat model that takes audio, <provider>:<model> (default: the audio model of "
                                   "the ai_models config)")
    c.add_argument("--out-dir", help="Report directory (default: <input folder>/analysis)")
    c.add_argument("--jobs", type=int, default=4, help="Clips analysed in parallel (default 4)")
    c.set_defaults(func=_cmd_analyze)

    routes.command(sub, ROUTE_TASKS)
    return p


def main(argv: list[str] | None = None) -> None:
    config.load_settings()
    args = _build_parser().parse_args(argv)
    sys.exit(args.func(args))
