"""Files to review: kind and MIME type by extension, size limits, video transcoding.

Kinds: text (sent as text with its path), image (PNG, JPEG, WebP), audio
(WAV, MP3, FLAC), video (MP4, MOV) and pdf, all sent inline. A file with
another extension is text when its first `PROBE_BYTES` decode as UTF-8, else
refused. Empty files are refused. A text file that is not valid UTF-8 is
sent with the bad bytes replaced and a warning on stderr.

The inline request limit is 20 MiB and base64 grows a file by 4/3, so the
files of one request may total `LIMIT_BYTES` (14 MiB, 18.7 MiB encoded). A
video over the limit, or every video (largest first) while the files of the
request total more than the limit, is transcoded by FFmpeg to 720p H.264
with AAC audio (`transcode_video`); any other file over the limit is refused
with its size, before it is read.
"""

from __future__ import annotations

import codecs
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

LIMIT_BYTES = 14 * 1024 * 1024
PROBE_BYTES = 64 * 1024
TRANSCODE_TIMEOUT_SECONDS = 900

TEXT_EXTENSIONS = {".md", ".txt", ".json", ".jsonl", ".csv", ".tsv", ".html", ".htm", ".xml", ".py",
                   ".yaml", ".yml", ".toml", ".js", ".ts", ".css", ".sh", ".srt", ".vtt", ".log"}
BINARY_TYPES = {
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".wav": ("audio", "audio/wav"),
    ".mp3": ("audio", "audio/mpeg"),
    ".flac": ("audio", "audio/flac"),
    ".mp4": ("video", "video/mp4"),
    ".mov": ("video", "video/quicktime"),
    ".pdf": ("pdf", "application/pdf"),
}

# FFmpeg settings for a video over the limit: at most 720 lines, H.264, AAC
TRANSCODE_ARGS = ["-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"]


class FileError(ValueError):
    """A file that cannot be sent."""


@dataclass
class ReviewFile:
    path: str            # as given on the command line
    kind: str            # text, image, audio, video, pdf
    mime: str
    data: bytes
    text: str | None = None
    transcoded: dict | None = field(default=None)  # original size and type when transcoded

    @property
    def size(self) -> int:
        return len(self.data)

    def record(self) -> dict:
        r = {"path": self.path, "kind": self.kind, "mime_type": self.mime, "bytes_sent": self.size}
        if self.transcoded:
            r["transcoded_from"] = self.transcoded
        return r


def mib(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MiB"


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)


def _read(path: Path, n: int | None = None) -> bytes:
    try:
        with path.open("rb") as fh:
            return fh.read() if n is None else fh.read(n)
    except OSError as e:
        raise FileError(f"{path}: cannot read: {e.strerror or e}") from None


def classify(path: Path) -> tuple[str, str]:
    """(kind, MIME type) by extension; text for an unknown extension whose
    first PROBE_BYTES decode as UTF-8 (a character cut at the end is allowed)."""
    ext = path.suffix.lower()
    if ext in BINARY_TYPES:
        return BINARY_TYPES[ext]
    if ext in TEXT_EXTENSIONS:
        return "text", "text/plain"
    try:
        codecs.getincrementaldecoder("utf-8")().decode(_read(path, PROBE_BYTES), final=False)
    except UnicodeDecodeError:
        raise FileError(f"{path}: unsupported file type {ext or '(no extension)'}; "
                        f"send text, PNG, JPEG, WebP, WAV, MP3, FLAC, MP4, MOV or PDF") from None
    return "text", "text/plain"


def transcode_video(path: Path, out: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileError(f"{path}: needs transcoding to fit the {mib(LIMIT_BYTES)} inline limit "
                        f"and ffmpeg is not on PATH")
    try:
        proc = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(path), *TRANSCODE_ARGS,
                               str(out)], stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=TRANSCODE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise FileError(f"ffmpeg did not finish transcoding {path} in {TRANSCODE_TIMEOUT_SECONDS} s") from None
    if proc.returncode != 0:
        raise FileError(f"ffmpeg could not transcode {path}: {proc.stderr.decode(errors='replace')[-300:]}")


def transcode(f: ReviewFile, limit: int) -> None:
    """Replace a video's data by its 720p transcode; refuse it when still over `limit`."""
    src = Path(f.path)
    with tempfile.TemporaryDirectory(prefix="second-opinion-") as tmp:
        out = Path(tmp) / "video.mp4"
        transcode_video(src, out)
        data = out.read_bytes()
    if len(data) > limit:
        raise FileError(f"{f.path}: {mib(src.stat().st_size)}, still {mib(len(data))} after transcoding to "
                        f"720p, over the {mib(limit)} inline limit; send a shorter clip")
    f.transcoded = {"bytes": src.stat().st_size, "mime_type": f.mime}
    f.data, f.mime = data, "video/mp4"


def load(path_str: str, limit: int = LIMIT_BYTES) -> ReviewFile:
    """The file as it will be sent. A video over `limit` is transcoded; any
    other file over `limit`, or a transcoded video still over it, is refused."""
    path = Path(path_str)
    if not path.is_file():
        raise FileError(f"{path_str}: no such file")
    size = path.stat().st_size
    if size == 0:
        raise FileError(f"{path_str}: empty file")
    kind, mime = classify(path)
    if size > limit:
        if kind != "video":
            raise FileError(f"{path_str}: {mib(size)} is over the {mib(limit)} inline limit")
        f = ReviewFile(path_str, kind, mime, b"")
        transcode(f, limit)
        return f
    data = _read(path)
    text = None
    if kind == "text":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            warn(f"{path_str} is not valid UTF-8 (byte {e.start}); invalid bytes are sent as U+FFFD")
            text = data.decode("utf-8", errors="replace")
    return ReviewFile(path_str, kind, mime, data, text)


def load_all(paths: list[str], limit: int = LIMIT_BYTES) -> list[ReviewFile]:
    """Every file. While the total is over `limit`, videos not yet transcoded
    are transcoded, largest first; a set still over the limit is refused."""
    files = [load(p, limit) for p in paths]
    videos = sorted((f for f in files if f.kind == "video" and not f.transcoded), key=lambda f: -f.size)
    for v in videos:
        if sum(f.size for f in files) <= limit:
            break
        transcode(v, limit)
    total = sum(f.size for f in files)
    if total > limit:
        sizes = ", ".join(f"{f.path} {mib(f.size)}" for f in files)
        raise FileError(f"the files total {mib(total)}, over the {mib(limit)} inline limit of one request "
                        f"({sizes}); review them in several runs")
    return files
