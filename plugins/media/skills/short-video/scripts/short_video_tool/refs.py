"""`refs`: the measurable part of a reference video or reference images, for
the agent that writes the project's `reference.md` (references/reference-video.md).

For a video, into `<out>/<video stem>/`:
- `t<sec>.png`: full-size frames at a fixed rate (`--fps`, default 4),
- `cut<sec>.png`: full-size frames at scene changes (FFmpeg `scene` score
  above 0.3),
- `sheet_<nn>.png`: contact sheets of `SHEET` frames each, in time order,
  each frame labelled with its time.
For images, into `<out>/images/`: the images copied and sheeted, labelled
with their file names.

`<out>/refs.json` holds per source: duration, size, fps, the frame list with
each frame's median colour, the scene-change times, a motion curve (mean
absolute difference between consecutive frames sampled at `MOTION_FPS`,
0 to 1), and the dominant colours (k-means, hex and share of pixels) per
sheet and over the whole source. A second run replaces the entry of the
same source and keeps the others.
"""

from __future__ import annotations

import json
import re
import shutil
from enum import Enum
from pathlib import Path

import numpy as np

from . import media

FPS = 4.0
SCENE = 0.3  # FFmpeg scene score above which a frame is a scene change
SHEET_COLUMNS = 4
SHEET_ROWS = 3
SHEET = SHEET_COLUMNS * SHEET_ROWS
THUMB_W = 480
SMALL_W, SMALL_H = 64, 36  # per-frame size for colour measurements
MOTION_FPS = 12.0
MOTION_W, MOTION_H = 96, 54
COLOURS = 6  # k-means clusters per palette
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
INDEX = "refs.json"


class FrameKind(str, Enum):
    RATE = "rate"  # a frame of the fixed-rate series
    CUT = "cut"  # a frame at a scene change


class RefsError(Exception):
    """The source is missing or holds nothing to analyse."""


def stamp(t: float) -> str:
    """Seconds in a file name: 3.25 -> '003.250'."""
    return f"{t:07.3f}"


def hex_colour(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(round(float(c))) for c in rgb)


def palette(pixels: np.ndarray, k: int = COLOURS, iters: int = 20) -> list[dict]:
    """Dominant colours of RGB `pixels` (N x 3): k-means with a fixed seed;
    clusters sorted by share, each {"hex", "share"}."""
    px = np.asarray(pixels, dtype=np.float64).reshape(-1, 3)
    if len(px) == 0:
        return []
    k = min(k, len(np.unique(px, axis=0)))
    rng = np.random.default_rng(0)
    # k-means++ seeding
    centres = [px[rng.integers(len(px))]]
    for _ in range(1, k):
        d = np.min(((px[:, None, :] - np.array(centres)[None]) ** 2).sum(-1), axis=1)
        centres.append(px[rng.choice(len(px), p=d / d.sum())] if d.sum() > 0 else px[0])
    c = np.array(centres)
    for _ in range(iters):
        label = np.argmin(((px[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
        new = np.array([px[label == i].mean(0) if np.any(label == i) else c[i] for i in range(k)])
        if np.allclose(new, c, atol=0.5):
            c = new
            break
        c = new
    label = np.argmin(((px[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
    share = np.bincount(label, minlength=k) / len(px)
    order = np.argsort(-share)
    return [{"hex": hex_colour(c[i]), "share": round(float(share[i]), 3)} for i in order if share[i] > 0]


def motion_curve(frames: np.ndarray, fps: float) -> list[list[float]]:
    """[t, mean |frame(t) - frame(t - 1/fps)| / 255] for each frame after the
    first; `frames` is (N, H, W) grey."""
    f = frames.astype(np.float32)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2)) / 255.0
    return [[round((i + 1) / fps, 3), round(float(v), 4)] for i, v in enumerate(d)]


def _label(text: str) -> str:
    """Text safe for an FFmpeg drawtext value."""
    return re.sub(r"[^A-Za-z0-9 ._-]", "_", text)


def _probe_video(path: Path) -> dict:
    info = media.probe(path)
    s = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    if s is None:
        raise RefsError(f"{path} has no video stream")
    num, _, den = s.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    dur = float(s.get("duration") or info["format"]["duration"])
    return {"width": int(s["width"]), "height": int(s["height"]), "fps": round(fps, 3), "duration": round(dur, 3)}


def _sheet(items: list[tuple[Path, str]], out: Path, thumb: tuple[int, int]) -> np.ndarray:
    """Write a contact sheet of `items` (file, label) to `out`; return the
    items' small RGB pixels, (n, SMALL_H, SMALL_W, 3)."""
    n = len(items)
    tw, th = thumb
    cmd: list = [media.which("ffmpeg"), "-v", "error", "-y"]
    for f, _ in items:
        cmd += ["-i", f]
    parts, big, small = [], [], []
    for i, (_, label) in enumerate(items):
        parts.append(
            f"[{i}:v]format=rgb24,split[a{i}][b{i}];"
            f"[a{i}]scale={tw}:{th}:force_original_aspect_ratio=decrease,"
            f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=0x202020,"
            f"drawtext=text='{_label(label)}':x=6:y=h-th-8:fontsize=20:fontcolor=white:"
            f"box=1:boxcolor=black@0.65:boxborderw=6[t{i}];"
            f"[b{i}]scale={SMALL_W}:{SMALL_H}[s{i}]")
        big.append(f"[t{i}]")
        small.append(f"[s{i}]")
    cols = min(SHEET_COLUMNS, n)
    if n == 1:
        parts.append("[t0]null[sheet];[s0]null[small]")
    else:
        layout = "|".join(f"{(i % cols) * tw}_{(i // cols) * th}" for i in range(n))
        parts.append(f"{''.join(big)}xstack=inputs={n}:layout={layout}:fill=0x101010[sheet];"
                     f"{''.join(small)}vstack=inputs={n}[small]")
    cmd += ["-filter_complex", ";".join(parts),
            "-map", "[sheet]", "-frames:v", "1", out,
            "-map", "[small]", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = media.run(cmd, text=False).stdout
    return np.frombuffer(raw, np.uint8).reshape(n, SMALL_H, SMALL_W, 3)


def _sheets(entries: list[dict], folder: Path, labels: list[str], thumb: tuple[int, int]) -> tuple[list[dict], np.ndarray]:
    """Contact sheets of `entries` (each with "file"), SHEET per sheet; sets
    each entry's "median"; returns the sheet records and all small pixels."""
    sheets, pixels = [], []
    for k in range(0, len(entries), SHEET):
        chunk = entries[k:k + SHEET]
        name = f"sheet_{k // SHEET + 1:02d}.png"
        small = _sheet([(folder / e["file"], lab) for e, lab in zip(chunk, labels[k:k + SHEET])],
                       folder / name, thumb)
        for e, px in zip(chunk, small):
            e["median"] = hex_colour(np.median(px.reshape(-1, 3), axis=0))
        sheets.append({"file": name, "frames": [e["file"] for e in chunk], "palette": palette(small)})
        pixels.append(small)
    return sheets, np.concatenate(pixels) if pixels else np.zeros((0, SMALL_H, SMALL_W, 3), np.uint8)


def _video(src: Path, folder: Path, fps: float) -> dict:
    meta = _probe_video(src)
    ffmpeg = media.which("ffmpeg")
    tmp = folder / "_tmp"
    tmp.mkdir()
    # fixed-rate frames: frame i is at i / fps
    media.run([ffmpeg, "-v", "error", "-i", src, "-vf", f"fps={fps}", "-start_number", "0", tmp / "r%05d.png"])
    frames = []
    for p in sorted(tmp.glob("r*.png")):
        t = int(p.stem[1:]) / fps
        if t > meta["duration"] + 1e-6:
            p.unlink()
            continue
        name = f"t{stamp(t)}.png"
        p.rename(folder / name)
        frames.append({"file": name, "t": round(t, 3), "kind": FrameKind.RATE.value})
    # scene changes: showinfo logs each selected frame's pts_time
    proc = media.run([ffmpeg, "-v", "info", "-i", src, "-vf", f"select='gt(scene,{SCENE})',showinfo",
                      "-fps_mode", "vfr", tmp / "c%05d.png"])
    times = [float(m) for m in re.findall(r"pts_time:\s*([0-9.]+)", proc.stderr)]
    cuts = []
    for p, t in zip(sorted(tmp.glob("c*.png")), times):
        name = f"cut{stamp(t)}.png"
        p.rename(folder / name)
        frames.append({"file": name, "t": round(t, 3), "kind": FrameKind.CUT.value})
        cuts.append(round(t, 3))
    shutil.rmtree(tmp)
    frames.sort(key=lambda e: (e["t"], e["kind"]))
    if not frames:
        raise RefsError(f"no frames decoded from {src}")
    labels = [("cut " if e["kind"] == FrameKind.CUT.value else "") + f"{e['t']:.2f} s" for e in frames]
    thumb = (THUMB_W, round(THUMB_W * meta["height"] / meta["width"] / 2) * 2)
    sheets, pixels = _sheets(frames, folder, labels, thumb)
    # motion curve on small grey frames
    raw = media.run([ffmpeg, "-v", "error", "-i", src, "-vf", f"fps={MOTION_FPS},scale={MOTION_W}:{MOTION_H}",
                     "-f", "rawvideo", "-pix_fmt", "gray", "-"], text=False).stdout
    grey = np.frombuffer(raw, np.uint8).reshape(-1, MOTION_H, MOTION_W)
    return {"kind": "video", **meta, "frame_fps": fps, "scene_threshold": SCENE, "cuts": cuts,
            "frames": frames, "sheets": sheets, "palette": palette(pixels),
            "motion": {"fps": MOTION_FPS, "values": motion_curve(grey, MOTION_FPS)}}


def _images(files: list[Path], folder: Path) -> dict:
    images = []
    for f in files:
        shutil.copy2(f, folder / f.name)
        s = next(s for s in media.probe(f)["streams"] if s.get("codec_type") == "video")
        images.append({"file": f.name, "src": str(f), "width": int(s["width"]), "height": int(s["height"])})
    sheets, pixels = _sheets(images, folder, [e["file"] for e in images], (THUMB_W, THUMB_W * 9 // 16))
    return {"kind": "images", "images": images, "sheets": sheets, "palette": palette(pixels)}


def _fresh(folder: Path) -> Path:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    return folder


def run(src: Path, out: Path, fps: float = FPS) -> dict:
    """Analyse `src` (a video, an image, or a folder of both) into `out`;
    update and return the index `out/refs.json`."""
    src = Path(src).expanduser().resolve()
    if not src.exists():
        raise RefsError(f"{src} does not exist")
    if fps <= 0:
        raise RefsError("--fps must be positive")
    files = sorted(p for p in src.iterdir() if p.is_file()) if src.is_dir() else [src]
    videos = [p for p in files if p.suffix.lower() in VIDEO_EXT]
    images = [p for p in files if p.suffix.lower() in IMAGE_EXT]
    if not videos and not images:
        raise RefsError(f"{src}: no video ({', '.join(sorted(VIDEO_EXT))}) or image "
                        f"({', '.join(sorted(IMAGE_EXT))}) found")
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / INDEX
    index = json.loads(index_path.read_text()) if index_path.is_file() else {"sources": []}
    done = []
    for v in videos:
        entry = {"src": str(v), "dir": v.stem, **_video(v, _fresh(out / v.stem), fps)}
        done.append(entry)
    if images:
        name = "images" if src.is_file() else f"images_{src.name}"
        done.append({"src": str(src), "dir": name, **_images(images, _fresh(out / name))})
    dirs = {e["dir"] for e in done}
    index["sources"] = [e for e in index["sources"] if e["dir"] not in dirs] + done
    index_path.write_text(json.dumps(index, indent=1) + "\n")
    return index


def summary(index: dict, out: Path, src: Path) -> list[str]:
    """The sheets of the sources made from `src`, one path per line, then the
    index path: what `refs` prints."""
    src = Path(src).expanduser().resolve()
    lines = []
    for e in index["sources"]:
        if Path(e["src"]) != src and Path(e["src"]).parent != src:
            continue
        for s in e["sheets"]:
            lines.append(str(out / e["dir"] / s["file"]))
    lines.append(str(out / INDEX))
    return lines
