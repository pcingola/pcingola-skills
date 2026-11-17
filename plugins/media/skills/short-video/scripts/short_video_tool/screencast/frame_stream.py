"""A video read forward in one FFmpeg pass as frames are asked for, holding only the last frame returned
(a 3 s 4K interval held whole takes about 2.2 GB). A request before the last one restarts the pass there.
Black frames read are recorded for the shot's warning."""

from __future__ import annotations

import subprocess

import cv2
import numpy as np

from .. import media

# A frame whose mean luma (0..255) is below this counts as black: a native dropdown or a page load in the
# recording. Dark UIs sit well above it.
BLACK_LUMA = 6.0


class FrameStream:
    def __init__(self, path, width: int, height: int, fps: float, duration: float):
        self.path, self.w, self.h, self.fps = path, width, height, fps
        self.last_t = max(0.0, duration - 0.5 / fps)
        self.proc: subprocess.Popen | None = None
        self.t0 = 0.0
        self.pos = -1                  # index (from t0) of the frame in self.frame
        self.frame: np.ndarray | None = None
        self.black: set[float] = set()

    def start(self, t: float) -> None:
        self.close()
        self.t0 = max(0.0, t - 0.05)
        self.proc = subprocess.Popen(
            [media.which("ffmpeg"), "-v", "error", "-ss", f"{self.t0:.3f}", "-i", str(self.path),
             "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.pos, self.frame = -1, None

    def at(self, t: float) -> np.ndarray:
        """The frame nearest recording time t (clamped to the video)."""
        t = min(max(t, 0.0), self.last_t)
        if self.proc is None or round((t - self.t0) * self.fps) < self.pos:
            self.start(t)
        target = int(round((t - self.t0) * self.fps))
        n = self.w * self.h * 3
        while self.pos < target:
            buf = self.proc.stdout.read(n)
            if len(buf) < n:
                break
            self.pos += 1
            self.frame = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        if self.frame is None:
            raise ValueError(f"{self.path}: no frame decoded at {t:.2f} s")
        small = cv2.resize(self.frame, (64, 36), interpolation=cv2.INTER_AREA)
        if float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).mean()) < BLACK_LUMA:
            self.black.add(round(t, 2))
        return self.frame

    def close(self) -> None:
        if self.proc is not None:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc.wait()
            self.proc = None
