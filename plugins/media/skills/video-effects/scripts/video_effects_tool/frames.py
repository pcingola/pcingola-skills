"""Shared clip machinery: easing, image loading and cover fit, the clip timeline
(holds, transformation, push-in), H.264 encoding over a pipe, the frame strip
and the JSON sidecar.

Images are BGR. Keys are uint8 on the work canvas (a quarter of the memory of
float32); transformation frames are float32, rounded once to uint8 on output.
The work canvas is the output size times (1 + push_in), so a pushed-in frame is
a 1:1 crop of it.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

STRIP_FRAMES = 6
STRIP_COLUMNS = 3
STRIP_TILE_WIDTH = 640
ASPECT_TOLERANCE = 0.02
MAX_SIDE = 7680
MAX_PUSH_IN = 0.5
STRIP_SUFFIXES = (".png", ".jpg", ".jpeg")
X264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


class EffectError(Exception):
    """An input or option the tool refuses; printed as one error line."""


def smoothstep(t):
    """3t^2 - 2t^3 on [0, 1], clipped outside; scalars or arrays."""
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# Reference work canvas of the tuned constants (blur sigmas, flow tolerance);
# they scale with sqrt(canvas area / reference area).
REF_CANVAS = (2304, 1296)


def canvas_scale(width: int, height: int) -> float:
    return math.sqrt(width * height / (REF_CANVAS[0] * REF_CANVAS[1]))


def parse_size(text: str) -> tuple[int, int]:
    """'1920x1080' -> (1920, 1080); both sides positive and even (yuv420p)."""
    parts = text.lower().split("x")
    try:
        w, h = (int(p) for p in parts)
    except ValueError:
        raise EffectError(f"bad size {text!r}: expected WxH, for example 1920x1080") from None
    if w <= 0 or h <= 0 or w % 2 or h % 2:
        raise EffectError(f"bad size {text!r}: width and height must be positive and even")
    if max(w, h) > MAX_SIDE:
        raise EffectError(f"bad size {text!r}: at most {MAX_SIDE} px per side")
    return w, h


def load_image(path: Path) -> np.ndarray:
    """The image at `path` as uint8 BGR."""
    if not path.is_file():
        raise EffectError(f"no such file: {path}")
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise EffectError(f"cannot read image: {path}")
    return img


def aspect_differs(img: np.ndarray, width: int, height: int) -> bool:
    ih, iw = img.shape[:2]
    return abs((iw / ih) / (width / height) - 1) > ASPECT_TOLERANCE


def cover_fit(img: np.ndarray, width: int, height: int) -> np.ndarray:
    """Centre crop to the aspect of width x height, then resize: no squash.
    Returns the input dtype (uint8 for a loaded image)."""
    ih, iw = img.shape[:2]
    target = width / height
    if iw / ih > target:
        cw, ch = max(1, round(ih * target)), ih
    else:
        cw, ch = iw, max(1, round(iw / target))
    x0, y0 = (iw - cw) // 2, (ih - ch) // 2
    crop = img[y0:y0 + ch, x0:x0 + cw]
    interp = cv2.INTER_AREA if cw >= width else cv2.INTER_CUBIC
    return cv2.resize(crop, (width, height), interpolation=interp)


@dataclass(frozen=True)
class Clip:
    """Output size, fps and timeline of one clip."""

    width: int
    height: int
    fps: float
    trans: float
    hold_start: float
    hold_end: float
    push_in: float

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise EffectError("--fps must be positive")
        if self.trans <= 0:
            raise EffectError("--trans must be positive")
        if self.hold_start < 0 or self.hold_end < 0:
            raise EffectError("holds must be zero or positive")
        if not 0 <= self.push_in <= MAX_PUSH_IN:
            raise EffectError(f"--push-in must be in [0, {MAX_PUSH_IN}]")
        if self.n_trans < 2:
            raise EffectError("--trans * --fps must give at least 2 frames")

    @property
    def n_trans(self) -> int:
        return round(self.trans * self.fps)

    @property
    def n_hold_start(self) -> int:
        return round(self.hold_start * self.fps)

    @property
    def n_hold_end(self) -> int:
        return round(self.hold_end * self.fps)

    @property
    def total(self) -> int:
        return self.n_hold_start + self.n_trans + self.n_hold_end

    @property
    def canvas(self) -> tuple[int, int]:
        """(width, height) of the work canvas."""
        return round(self.width * (1 + self.push_in)), round(self.height * (1 + self.push_in))

    def zoom(self, k: int) -> float:
        """Push-in zoom of output frame k: smoothstep from 1 to 1 + push_in."""
        return 1.0 + self.push_in * float(smoothstep(k / max(1, self.total - 1)))

    def strip_indices(self) -> list[int]:
        """Output frame indices of the strip: evenly spaced over the transformation."""
        picks = np.linspace(0, self.n_trans - 1, STRIP_FRAMES).round().astype(int)
        return [self.n_hold_start + int(i) for i in picks]


def push(canvas_img: np.ndarray, clip: Clip, z: float) -> np.ndarray:
    """Centred crop of the canvas at zoom z (1 = the whole canvas), scaled to
    the output size; uint8."""
    cw, ch = clip.canvas
    w, h = cw / z, ch / z
    x0, y0 = (cw - w) / 2, (ch - h) / 2
    sx, sy = clip.width / w, clip.height / h
    m = np.float32([[sx, 0, (0.5 - x0) * sx - 0.5], [0, sy, (0.5 - y0) * sy - 0.5]])
    out = cv2.warpAffine(canvas_img, m, (clip.width, clip.height), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_REPLICATE)
    return np.clip(out, 0, 255).round().astype(np.uint8) if out.dtype != np.uint8 else out


def clip_frames(clip: Clip, start: np.ndarray, end: np.ndarray,
                trans_frame: Callable[[float], np.ndarray]) -> Iterator[np.ndarray]:
    """Every output frame: hold on `start`, the transformation (trans_frame(t),
    t from 0 to 1, one call per frame), hold on `end`; push-in over all."""
    hs, n = clip.n_hold_start, clip.n_trans
    for k in range(clip.total):
        if k < hs:
            img = start
        elif k < hs + n:
            img = trans_frame((k - hs) / (n - 1))
        else:
            img = end
        yield push(img, clip, clip.zoom(k))


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise EffectError("ffmpeg not found on PATH (macOS: brew install ffmpeg)")
    return path


def ffmpeg_version() -> str:
    out = subprocess.run([ffmpeg_path(), "-version"], capture_output=True, text=True).stdout
    first = out.splitlines()[0] if out else ""
    return first.split()[2] if first.startswith("ffmpeg version") else first


def strip_image(tiles: list[np.ndarray]) -> np.ndarray:
    rows = [np.hstack(tiles[i:i + STRIP_COLUMNS]) for i in range(0, len(tiles), STRIP_COLUMNS)]
    return np.vstack(rows)


def tile(frame: np.ndarray, clip: Clip) -> np.ndarray:
    th = round(STRIP_TILE_WIDTH * clip.height / clip.width)
    return cv2.resize(frame, (STRIP_TILE_WIDTH, th), interpolation=cv2.INTER_AREA)


def encode(frames: Iterator[np.ndarray], clip: Clip, out: Path, strip: Path) -> int:
    """Pipe raw frames to FFmpeg (H.264, yuv420p, no audio) and write the strip.
    Returns the number of frames written. On any failure the partial MP4 and
    strip are removed."""
    try:
        return _encode(frames, clip, out, strip)
    except BaseException:
        out.unlink(missing_ok=True)
        strip.unlink(missing_ok=True)
        raise


def _encode(frames: Iterator[np.ndarray], clip: Clip, out: Path, strip: Path) -> int:
    cmd = [ffmpeg_path(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{clip.width}x{clip.height}", "-r", f"{clip.fps:g}", "-i", "-", "-an", *X264, str(out)]
    picks = clip.strip_indices()
    tiles: list[np.ndarray] = []
    count = 0
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
        ok = False
        try:
            for k, frame in enumerate(frames):
                proc.stdin.write(frame.tobytes())
                tiles.extend(tile(frame, clip) for _ in range(picks.count(k)))
                count += 1
            ok = True
        except BrokenPipeError:
            pass  # FFmpeg exited early; its code and stderr are reported below
        except BaseException:
            proc.kill()
            raise
        finally:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
            code = proc.wait()
        if code != 0 or not ok:
            err.seek(0)
            raise EffectError(f"ffmpeg failed ({code}): {err.read().decode(errors='replace').strip()}")
    if not cv2.imwrite(str(strip), strip_image(tiles)):
        raise EffectError(f"cannot write {strip}")
    return count


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def default_strip(out: Path) -> Path:
    return out.with_name(f"{out.stem}_frames.png")


def sidecar_path(out: Path) -> Path:
    return out.with_name(out.name + ".json")


def check_writable(paths: list[Path], force: bool) -> None:
    """Refuse existing outputs without force; create parent directories."""
    existing = [str(p) for p in paths if p.exists()]
    if existing and not force:
        raise EffectError(f"output exists (use --force to replace): {', '.join(existing)}")
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
