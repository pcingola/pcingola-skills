"""Perspective projection of page points into the frame."""

from __future__ import annotations

import math

import numpy as np

from .model import CameraKey, Point, Rect


class Projection:
    """Page points to frame points for a camera key: the page turned about the key's centre (yaw, then
    pitch), seen in perspective at focal length `focal` frame widths, scaled by the zoom."""

    def __init__(self, frame: tuple[int, int], focal: float):
        self.w, self.h = frame
        self.f = focal * self.w

    def __call__(self, pts: np.ndarray | list[Point], cam: CameraKey) -> np.ndarray:
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        q = pts - np.array(cam.center)
        yaw, pitch = math.radians(cam.yaw), math.radians(cam.pitch)
        x, y = q[:, 0], q[:, 1]
        X = x * math.cos(yaw)
        Z = -x * math.sin(yaw)
        Y = y * math.cos(pitch) - Z * math.sin(pitch)
        Z = y * math.sin(pitch) + Z * math.cos(pitch)
        d = self.f / (self.f + Z)
        return np.stack([X * d * cam.zoom + self.w / 2, Y * d * cam.zoom + self.h / 2], 1)

    def quad(self, rect: Rect, cam: CameraKey) -> np.ndarray:
        x, y, w, h = rect
        return self([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], cam)
