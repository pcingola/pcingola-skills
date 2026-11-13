"""frames: easing, size parsing, cover fit, timeline, push-in, strip."""

import shutil
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from video_effects_tool.frames import (Clip, EffectError, aspect_differs, clip_frames, cover_fit, encode,
                                       parse_size, smoothstep)

from .images import gradient
from tests.prereq import requires


def clip(**kw) -> Clip:
    base = dict(width=96, height=54, fps=10, trans=1.0, hold_start=0.5, hold_end=0.3, push_in=0.08)
    base.update(kw)
    return Clip(**base)


class TestEasing(unittest.TestCase):
    def test_smoothstep(self) -> None:
        """frames.smoothstep at fixed points, clipping outside [0, 1] and monotonicity. Every effect and the
        push-in ease through it, so a wrong curve changes every clip."""
        self.assertEqual(float(smoothstep(0)), 0)
        self.assertEqual(float(smoothstep(1)), 1)
        self.assertAlmostEqual(float(smoothstep(0.5)), 0.5)
        self.assertAlmostEqual(float(smoothstep(0.25)), 0.15625)
        self.assertEqual(float(smoothstep(-1)), 0)
        self.assertEqual(float(smoothstep(2)), 1)
        t = np.linspace(0, 1, 50)
        self.assertTrue(np.all(np.diff(smoothstep(t)) >= 0))


class TestSize(unittest.TestCase):
    def test_parse(self) -> None:
        """frames.parse_size reads WxH for landscape and portrait sizes. Guards the order of width and height
        passed to FFmpeg and the canvas."""
        self.assertEqual(parse_size("1920x1080"), (1920, 1080))
        self.assertEqual(parse_size("1080x1920"), (1080, 1920))

    def test_bad(self) -> None:
        """frames.parse_size refuses malformed, non-positive, odd and three-part sizes. yuv420p needs even
        sides, and a bad size must be one error line, not an FFmpeg failure."""
        for text in ("1920", "axb", "0x100", "-2x4", "101x100", "1920x1080x3"):
            with self.assertRaises(EffectError, msg=text):
                parse_size(text)


class TestCoverFit(unittest.TestCase):
    def test_centre_crop_no_squash(self) -> None:
        """frames.cover_fit centre-crops a wide image to the target aspect without squashing, for square and
        tall targets. Guards the cover-fit rule (centre crop, no squash) of the effects."""
        img = np.zeros((100, 300, 3), np.uint8)
        img[:, 100:200] = 255  # centre third white
        out = cover_fit(img, 100, 100)
        self.assertEqual(out.shape, (100, 100, 3))
        self.assertTrue(np.all(out > 250))
        tall = cover_fit(img, 50, 100)
        self.assertEqual(tall.shape, (100, 50, 3))

    def test_aspect_check(self) -> None:
        """frames.aspect_differs accepts a 2720x1536 image for 1920x1080 and flags a square one. Guards the 2 %
        tolerance that decides the centre-crop warning."""
        self.assertFalse(aspect_differs(np.zeros((1536, 2720, 3)), 1920, 1080))
        self.assertTrue(aspect_differs(np.zeros((100, 100, 3)), 1920, 1080))


class TestClip(unittest.TestCase):
    def test_counts(self) -> None:
        """Clip frame counts for transformation, holds and total from seconds and fps. The sidecar, strip and
        encoded frame count depend on these."""
        c = clip(fps=30, trans=3.5, hold_start=1.5, hold_end=1.5)
        self.assertEqual(c.n_trans, 105)
        self.assertEqual(c.total, 105 + 45 + 45)
        c = clip(fps=30, trans=2.0, hold_start=0, hold_end=0.5)
        self.assertEqual(c.total, 60 + 15)

    def test_canvas(self) -> None:
        """Clip.canvas is the output size times 1 + push-in, rounded, and the output size without push-in.
        Guards the work canvas the keys are fitted to."""
        self.assertEqual(clip(width=1920, height=1080, push_in=0.08).canvas, (2074, 1166))
        self.assertEqual(clip(width=1080, height=1920, push_in=0).canvas, (1080, 1920))

    def test_refusals(self) -> None:
        """Clip refuses zero fps, non-positive transformation, negative holds, negative push-in and a
        transformation under 2 frames. Each would divide by zero or render an empty transformation."""
        for kw in ({"fps": 0}, {"trans": 0}, {"trans": -1}, {"hold_start": -1}, {"push_in": -0.1}, {"trans": 0.05}):
            with self.assertRaises(EffectError, msg=str(kw)):
                clip(**kw)

    def test_strip_indices(self) -> None:
        """Clip.strip_indices picks 6 frames from the first to the last transformation frame, after the start
        hold. Guards the strip showing the transformation, not the holds."""
        c = clip()
        idx = c.strip_indices()
        self.assertEqual(len(idx), 6)
        self.assertEqual(idx[0], c.n_hold_start)
        self.assertEqual(idx[-1], c.n_hold_start + c.n_trans - 1)


class TestPushIn(unittest.TestCase):
    def frames(self, c: Clip) -> list[np.ndarray]:
        self.start, self.end = gradient(150, 90), gradient(150, 90, flip=True)
        a, b = cover_fit(self.start, *c.canvas), cover_fit(self.end, *c.canvas)
        times = []

        def trans(t):
            times.append(t)
            return (1 - t) * a + t * b

        out = list(clip_frames(c, a, b, trans))
        self.times = times
        return out

    def test_first_frame_is_cover_fitted_start(self) -> None:
        """frames.clip_frames yields Clip.total frames and the first is the whole cover-fitted start image at
        zoom 1. Guards the push-in starting from the full image."""
        c = clip()
        out = self.frames(c)
        self.assertEqual(len(out), c.total)
        self.assertEqual(out[0].shape, (54, 96, 3))
        ref = cover_fit(self.start, 96, 54)
        self.assertLess(np.abs(out[0].astype(float) - ref).mean(), 2.0)

    def test_last_frame_is_centre_of_end(self) -> None:
        """frames.clip_frames ends on the centre crop of the end canvas at zoom 1 + push-in. Guards the push-in
        ending as a 1:1 crop of the work canvas."""
        c = clip()
        out = self.frames(c)
        canvas = cover_fit(self.end, *c.canvas)
        cw, ch = c.canvas
        x0, y0 = (cw - 96) // 2, (ch - 54) // 2
        ref = canvas[y0:y0 + 54, x0:x0 + 96]
        self.assertLess(np.abs(out[-1].astype(float) - ref).mean(), 2.0)

    def test_no_push_in_endpoints_exact(self) -> None:
        """frames.clip_frames with push-in 0 gives the cover-fitted start and end images exactly. Guards push-in
        0 as off."""
        c = clip(push_in=0)
        out = self.frames(c)
        self.assertLess(np.abs(out[0].astype(float) - cover_fit(self.start, 96, 54)).max(), 1.0)
        self.assertLess(np.abs(out[-1].astype(float) - cover_fit(self.end, 96, 54)).max(), 1.0)

    def test_one_call_per_transformation_frame(self) -> None:
        """frames.clip_frames calls the transformation once per transformation frame with distinct times from 0
        to 1. Guards the region effect and the flow chain, which compute each frame once in increasing time."""
        c = clip()
        self.frames(c)
        self.assertEqual(len(self.times), c.n_trans)
        self.assertEqual(len(set(self.times)), c.n_trans)
        self.assertEqual(self.times[0], 0)
        self.assertEqual(self.times[-1], 1)

    def test_vertical(self) -> None:
        """frames.clip_frames gives portrait frames for a portrait clip. Guards width and height not being
        swapped in push."""
        c = clip(width=54, height=96)
        out = self.frames(c)
        self.assertEqual(out[0].shape, (96, 54, 3))


@requires(shutil.which("ffmpeg"), "needs ffmpeg")
class TestEncode(unittest.TestCase):
    def test_strip_size_and_count(self) -> None:
        """frames.encode writes the MP4, returns the frame count and writes a 3x2 strip of 640-wide tiles.
        Guards the strip layout and the returned total that goes into the sidecar."""
        c = clip(width=96, height=54)
        a = cover_fit(gradient(96, 54), *c.canvas)
        b = cover_fit(gradient(96, 54, flip=True), *c.canvas)
        with tempfile.TemporaryDirectory() as tmp:
            out, strip = Path(tmp, "x.mp4"), Path(tmp, "x_frames.png")
            n = encode(clip_frames(c, a, b, lambda t: (1 - t) * a + t * b), c, out, strip)
            self.assertEqual(n, c.total)
            self.assertGreater(out.stat().st_size, 0)
            s = cv2.imread(str(strip))
            self.assertEqual(s.shape, (2 * 360, 3 * 640, 3))

    def test_strip_vertical(self) -> None:
        """frames.encode tiles a portrait clip at 640 px wide with height from the output aspect. Guards the
        tile height computed from the clip, not the canvas."""
        c = clip(width=54, height=96)
        a = cover_fit(gradient(96, 54), *c.canvas)
        with tempfile.TemporaryDirectory() as tmp:
            strip = Path(tmp, "v.png")
            encode(clip_frames(c, a, a, lambda t: a), c, Path(tmp, "v.mp4"), strip)
            self.assertEqual(cv2.imread(str(strip)).shape, (2 * 1138, 3 * 640, 3))
