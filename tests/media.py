"""Inputs and checks of the model server's integration tests: PNG images, the end of a video job, and the streams
of an MP4 read with PyAV."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass

import openai
from openai.types import Video
from PIL import Image

POLL_SECONDS = 0.2
WAIT_SECONDS = 25.0


def png(width: int, height: int, color=(200, 80, 40), mode: str = "RGB") -> bytes:
    """A PNG of one colour."""
    buf = io.BytesIO()
    Image.new(mode, (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def left_half_mask(width: int, height: int) -> bytes:
    """An OpenAI mask: opaque, with the left half transparent (the area to repaint)."""
    mask = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    mask.paste((0, 0, 0, 0), (0, 0, width // 2, height))
    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    return buf.getvalue()


@dataclass(frozen=True)
class Clip:
    """What an MP4 holds: the video stream's codec, size and frame count, and the audio stream's codec (None
    without one)."""

    video_codec: str
    width: int
    height: int
    frames: int
    audio_codec: str | None


def clip(data: bytes) -> Clip:
    """The streams of the MP4 `data`, read and decoded with PyAV."""
    import av

    with av.open(io.BytesIO(data)) as f:
        v = f.streams.video[0]
        audio = f.streams.audio[0].codec_context.name if f.streams.audio else None
        frames = sum(1 for _ in f.decode(v))
        return Clip(v.codec_context.name, v.codec_context.width, v.codec_context.height, frames, audio)


def frames(data: bytes) -> list[bytes]:
    """The decoded RGB frames of the MP4 `data`, read with PyAV."""
    import av

    with av.open(io.BytesIO(data)) as f:
        return [frame.to_ndarray(format="rgb24").tobytes() for frame in f.decode(f.streams.video[0])]


def finished(client: openai.OpenAI, video: Video) -> Video:
    """The job `video` once it is completed or failed, polled with `videos.retrieve`."""
    deadline = time.monotonic() + WAIT_SECONDS
    while video.status in ("queued", "in_progress"):
        assert time.monotonic() < deadline, f"video {video.id} still {video.status}"
        time.sleep(POLL_SECONDS)
        video = client.videos.retrieve(video.id)
    return video
