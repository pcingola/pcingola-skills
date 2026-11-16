"""Film assembly: concat scenes, duck the music under the voice, two-pass loudnorm,
and the creator caption (see `credit`) drawn in the same encode.

The filter graph is built by `build_filter_graph`, a pure function, so its
stages can be checked without running FFmpeg. Inputs are the scene files
(0..n-1) followed by the music (input n, read with `-stream_loop -1`), if any.
Without music the film carries the voice only.
"""

from __future__ import annotations

import json
import math
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import brand, credit, media, music, settings, state, storyboard, versions
from .media import num



def _m() -> dict:
    return settings.get()["mix"]


def _audio_format() -> str:
    return (f"aresample={_m()['sample_rate']},"
            f"aformat=sample_fmts=fltp:channel_layouts={settings.encode()['channel_layout']}")


class AssembleError(Exception):
    """The film cannot be assembled."""


@dataclass
class Loudness:
    """Values measured by the first `loudnorm` pass."""

    input_i: str
    input_tp: str
    input_lra: str
    input_thresh: str
    target_offset: str

    @property
    def silent(self) -> bool:
        """The mix has no sound (`input_i` is `-inf`): the second pass cannot normalise it."""
        return not math.isfinite(float(self.input_i))


def loudnorm_filter(measured: Loudness | None) -> str:
    m = _m()
    base = f"loudnorm=I={num(m['loudness_i'])}:TP={num(m['loudness_tp'])}:LRA={num(m['loudness_lra'])}"
    if measured is None:
        return base + ":print_format=json"
    if measured.silent:
        return "anull"  # a silent mix stays silent; loudnorm refuses measured_I=-inf
    return (
        f"{base}:measured_I={measured.input_i}:measured_TP={measured.input_tp}"
        f":measured_LRA={measured.input_lra}:measured_thresh={measured.input_thresh}"
        f":offset={measured.target_offset}:linear=true:print_format=summary"
    )


def build_filter_graph(
    scene_durations: list[float],
    music_db: float | None,
    measured: Loudness | None = None,
    video: bool = True,
    caption: str | None = None,
) -> str:
    """FFmpeg `-filter_complex` for the film.

    Outputs `[v]` (when `video`) and `[aout]`. With `measured=None` the
    loudnorm stage only measures (first pass); with values it applies them
    linearly (second pass). `caption` is a video filter (the credit
    `drawtext`) applied to the joined video. `music_db=None` means no music
    input: the voice goes straight to loudnorm.
    """
    n_scenes = len(scene_durations)
    if n_scenes < 1:
        raise ValueError("need at least one scene")
    s = _m()
    duration = sum(scene_durations)
    fade_out = min(s["fade_out"], duration / 2)
    fade_in = min(s["fade_in"], duration / 2)
    audio_format = _audio_format()
    # Each scene's voice is cut or padded to its video length, so the voice
    # track stays in sync and the film is exactly as long as its pictures.
    fit = [f"[{i}:a:0]atrim=0:{num(d)},apad=whole_dur={num(d)}[a{i}]" for i, d in enumerate(scene_durations)]
    if video:
        inputs = "".join(f"[{i}:v:0][a{i}]" for i in range(n_scenes))
        vout = "[vcat]" if caption else "[v]"
        concat = f"{inputs}concat=n={n_scenes}:v=1:a=1{vout}[voice_raw]"
        if caption:
            concat += f";[vcat]{caption}[v]"
    else:
        inputs = "".join(f"[a{i}]" for i in range(n_scenes))
        concat = f"{inputs}concat=n={n_scenes}:v=0:a=1[voice_raw]"
    if music_db is None:
        return ";".join([
            *fit,
            concat,
            f"[voice_raw]{audio_format},{loudnorm_filter(measured)},aresample={s['sample_rate']}[aout]",
        ])
    m = n_scenes
    return ";".join([
        *fit,
        concat,
        f"[voice_raw]{audio_format},asplit=2[voice][key]",
        f"[{m}:a:0]{audio_format},atrim=0:{num(duration)},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={num(fade_in)},"
        f"afade=t=out:st={num(duration - fade_out)}:d={num(fade_out)},"
        f"volume={num(music_db)}dB[music]",
        f"[music][key]{s['duck']}[ducked]",
        "[voice][ducked]amix=inputs=2:normalize=0:duration=first[mix]",
        f"[mix]{loudnorm_filter(measured)},aresample={s['sample_rate']}[aout]",
    ])


_LOUDNORM_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


def parse_loudnorm(stderr: str) -> Loudness:
    found = _LOUDNORM_JSON.findall(stderr)
    if not found:
        raise AssembleError("loudnorm printed no measurement")
    d = json.loads(found[-1])
    return Loudness(d["input_i"], d["input_tp"], d["input_lra"], d["input_thresh"], d["target_offset"])


def ffmpeg_inputs(scene_files: list[Path], music_file: Path | None) -> list[str]:
    args: list[str] = []
    for f in scene_files:
        args += ["-i", str(f)]
    if music_file is None:
        return args
    return args + ["-stream_loop", "-1", "-i", str(music_file)]


def mix(scene_files: list[Path], music_file: Path | None, out: Path, music_db: float,
        author: str | None = None, captioned: list[bool] | None = None, b: dict | None = None) -> dict:
    """Run both passes and write `out`; `music_file=None` gives a voice-only
    film. With `author`, draw the credit caption
    over the scenes marked in `captioned` (default: all), its colour chosen
    per scene from the corner's brightness, and write the metadata tags. With
    a brand `b` (see `brand.load`), its logo goes beside the caption, per
    scene the PNG for the caption's colour (`credit.Logo.png`); without an
    author the logo alone is drawn. With neither the film has no credit.
    Returns measurements for the manifest."""
    ffmpeg = media.which("ffmpeg")
    e = settings.encode()
    durations = [media.video_duration(f) for f in scene_files]
    total = sum(durations)
    inputs = ffmpeg_inputs(scene_files, music_file)
    if music_file is None:
        music_db = None

    first = media.run([
        ffmpeg, "-hide_banner", "-nostats", *inputs,
        "-filter_complex", build_filter_graph(durations, music_db, video=False),
        "-map", "[aout]", "-f", "null", "-",
    ])
    measured = parse_loudnorm(first.stderr)

    with tempfile.TemporaryDirectory() as d:
        caption, tags = None, []
        if author or b:
            frame = media.video_size(scene_files[0])
            logo = credit.caption_logo(b, frame, Path(d))
            region = credit.measured_region(logo, frame)
            colors = [
                credit.caption_color(credit.corner_luma(f, credit.sample_times(dur), region)) if on else None
                for f, dur, on in zip(scene_files, durations, captioned or [True] * len(scene_files))
            ]
            caption = credit.caption_filter(credit.write_caption(Path(d), author) if author else None,
                                            credit.caption_segments(durations, colors), logo)
            tags = credit.metadata_args(author) if author else []
        media.run([
            ffmpeg, "-y", "-hide_banner", "-nostats", "-v", "error", *inputs,
            "-filter_complex", build_filter_graph(durations, music_db, measured, caption=caption),
            "-map", "[v]", "-map", "[aout]",
            "-c:v", e["video_codec"], "-crf", str(e["crf"]), "-pix_fmt", e["pixel_format"],
            "-movflags", "+faststart",
            "-c:a", e["audio_codec"], "-b:a", str(e["audio_bitrate"]), "-ar", str(_m()["sample_rate"]), *tags,
            str(out),
        ])
    return {"scene_durations": [round(d, 3) for d in durations], "duration": round(total, 3),
            "measured_input_i": measured.input_i}


def music_source(project: Path, music_version: str | None) -> tuple[Path | None, Path | None]:
    """(version dir, file) of the music `assemble` uses; (None, None) for a voice-only film."""
    spec = settings.get()["music"]
    if not (music_version or spec.get("file")):
        return None, None
    mroot = music.music_root(project)
    mdir = mroot / music_version if music_version else versions.latest_version(mroot, require=state.META)
    if mdir is None or not mdir.is_dir():
        raise AssembleError("no music version; run `music` first")
    return mdir, music.music_file(mdir)


def sources(project: Path, data: dict, music_version: str | None = None) -> list[Path]:
    """The audio tracks `assemble` would mix: the narration of each scene's
    latest render (none for a silent clip scene), then the music file."""
    files = []
    for s in storyboard.scenes(data):
        sdir = state.latest_render(project, s["id"])
        voice = state.read_meta(sdir).get("voice_version") if sdir is not None else None
        if voice:
            files.append(state.voice_root(project, s["id"]) / voice / "narration.wav")
    mfile = music_source(project, music_version)[1]
    return files + ([mfile] if mfile else [])


def film_sources(project: Path, film: str) -> list[Path]:
    """The audio tracks film version `film` was mixed from, from its manifest."""
    m = json.loads((project / "film" / film / "manifest.json").read_text(encoding="utf-8"))
    files = [state.voice_root(project, e["id"]) / e["voice_version"] / "narration.wav"
             for e in m["scenes"] if e.get("voice_version")]
    if m.get("music"):
        files.append(music.music_root(project) / m["music"]["version"] / m["music"]["file"])
    return files


def assemble(project: Path, data: dict, music_version: str | None = None,
             brand_dir: Path | None = None) -> Path:
    """Assemble the latest rendered version of every scene plus a music
    version into `film/v<N>/film.mp4`. Music gain is `mix.music_db`; the
    author is `author:` (none: no caption); the logo beside the caption comes from the brand
    folder `brand_dir`, which must be the folder of the brand named by
    `brand:`. With no `music.file` set, and no version named, the film has the
    voice only."""
    music_db = _m()["music_db"]
    author = settings.author()
    name = settings.get().get("brand")
    if brand_dir is not None and not name:
        raise AssembleError(f"--brand {brand_dir} is given but no `brand:` is set in "
                            f"{project / settings.PROJECT_FILE}; set `brand: <name>` there first")
    try:
        b = brand.load(name, brand_dir)
    except ValueError as e:
        raise AssembleError(str(e)) from e
    unrendered = [s["id"] for s in storyboard.scenes(data) if state.latest_render(project, s["id"]) is None]
    if unrendered:
        raise AssembleError("no rendered version of scene(s): " + ", ".join(unrendered)
                            + "; run `render` first (a clip scene: `clip`)")

    mdir, mfile = music_source(project, music_version)

    entries, files = [], []
    for s in storyboard.scenes(data):
        sdir = state.latest_render(project, s["id"])
        meta = state.read_meta(sdir)
        files.append(sdir / "scene.mp4")
        entries.append({"id": s["id"], "scene_version": sdir.name, "voice_version": meta.get("voice_version")})

    out_dir = versions.next_version(project / "film")
    try:
        result = mix(files, mfile, out_dir / "film.mp4", music_db, author=author,
                     captioned=credit.captioned([storyboard.shows_author(s) for s in storyboard.scenes(data)]) if author else None,
                     b=b)
    except Exception:
        # Leave no half-written version behind; its number is still never reused.
        for p in out_dir.iterdir():
            p.unlink()
        out_dir.rmdir()
        raise
    for e, d in zip(entries, result["scene_durations"]):
        e["duration"] = d
    manifest = {
        "version": out_dir.name,
        "scenes": entries,
        "music": {"version": mdir.name, "file": mfile.name, "gain_db": music_db} if mdir else None,
        "duration": result["duration"],
        "author": author,
        "loudness": {"target_i": _m()["loudness_i"], "target_tp": _m()["loudness_tp"], "target_lra": _m()["loudness_lra"],
                     "measured_input_i": result["measured_input_i"]},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out_dir / "film.mp4"
