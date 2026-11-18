"""short_video_tool.screencast: the shot list format and its checks, the camera, typing, alignment, and
frames rendered from tiny PNG screenshots written with OpenCV (references/screencast.md of short-video).
Recordings go through FFmpeg and are tested in tests/integration/short_video/test_screencast.py."""
import math
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from short_video_tool import settings
from short_video_tool.screencast import ScreencastError, load, pictures
from short_video_tool.screencast.camera import Camera
from short_video_tool.screencast.model import CameraSpec, Typing
from short_video_tool.screencast.timeline import Timeline
from short_video_tool.screencast.typing_reveal import TypingReveal

W, H, FPS = 320, 180, 30
SETTINGS = f"video:\n  width: {W}\n  height: {H}\n  fps: {FPS}\n"


def page(path: Path, w: int = 640, h: int = 360) -> Path:
    """A light page with a dark text line, a blue button at page (40, 200)-(200, 260) and a red dot centred
    at (480, 120)."""
    img = np.full((h, w, 3), 235, np.uint8)
    cv2.rectangle(img, (40, 40), (600, 90), (255, 255, 255), -1)
    cv2.putText(img, "hello screencast", (50, 78), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 30), 2, cv2.LINE_AA)
    cv2.rectangle(img, (40, 200), (200, 260), (200, 120, 40), -1)
    cv2.circle(img, (480, 120), 20, (0, 0, 255), -1)
    cv2.imwrite(str(path), img)
    return path


def solid(path: Path, bgr: tuple[int, int, int], w: int = 320, h: int = 180) -> Path:
    cv2.imwrite(str(path), np.full((h, w, 3), bgr, np.uint8))
    return path


def red_centroid(img: np.ndarray) -> tuple[float, float, int]:
    """Centre and pixel count of the strongly red pixels of a BGR frame."""
    m = (img[..., 2] > 150) & (img[..., 1] < 90) & (img[..., 0] < 90)
    ys, xs = np.nonzero(m)
    return float(xs.mean()), float(ys.mean()), int(m.sum())


class ProjectCase(unittest.TestCase):
    """A temporary project folder whose settings.yaml sets a small `video:` frame."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "settings.yaml").write_text(SETTINGS)
        settings.use_project(self.dir)

    def tearDown(self) -> None:
        settings.use_project(None)
        self._tmp.cleanup()

    def shots(self, text: str) -> Path:
        p = self.dir / "shots.yaml"
        p.write_text(text)
        return p

    def timeline(self, text: str) -> Timeline:
        shots, style = load(self.shots(text))
        return Timeline(shots, style, warn=self.warnings.append)

    @property
    def warnings(self) -> list[str]:
        if not hasattr(self, "_warnings"):
            self._warnings = []
        return self._warnings

    def frame(self, tl: Timeline, t: float) -> np.ndarray:
        return next(iter(tl.frames([t])))[1]


class TestShotList(ProjectCase):

    def test_unknown_key_names_its_place(self) -> None:
        """screencast.load refuses an unknown key in a shot, naming the shot's index and the key. Guards a typo
        passing silently."""
        page(self.dir / "p.png")
        with self.assertRaises(ScreencastError) as cm:
            load(self.shots("shots:\n  - image: p.png\n    length: 1\n    zoom: 2\n"))
        self.assertIn("shots[0]: unknown key 'zoom'", str(cm.exception))

    def test_missing_file_and_kind_keys(self) -> None:
        """screencast.load refuses a missing source file and a key the shot's kind does not take, each with its
        place."""
        with self.assertRaises(ScreencastError) as cm:
            load(self.shots("shots:\n  - image: nope.png\n    length: 1\n"))
        self.assertIn("shots[0].image:", str(cm.exception))
        page(self.dir / "p.png")
        with self.assertRaises(ScreencastError) as cm:
            load(self.shots("shots:\n  - type: picture\n    image: p.png\n    length: 1\n    typing: []\n"))
        self.assertIn("a picture shot takes no `typing`", str(cm.exception))

    def test_typing_needs_a_screenshot(self) -> None:
        """screencast.load refuses `typing` on a recording shot and asks for an `image`. Guards typing, which is
        rebuilt from a screenshot of the finished text."""
        (self.dir / "r.mp4").write_bytes(b"")   # the parser checks only that the file exists
        with self.assertRaises(ScreencastError) as cm:
            load(self.shots("shots:\n  - video: r.mp4\n    length: 1\n    typing: [{rect: [0, 0, 10, 10]}]\n"))
        self.assertIn("give the shot an `image`", str(cm.exception))

    def test_colours_from_palette_and_style_override(self) -> None:
        """screencast.load resolves highlight colours from the palette (a list's `style:` overrides it), with
        `accent` as the default."""
        page(self.dir / "p.png")
        shots, style = load(self.shots(
            "style:\n  palette: {accent: '#FF0000', brand: '#00FF00'}\n"
            "shots:\n  - image: p.png\n    length: 1\n"
            "    highlights: [{rect: [1, 1, 5, 5]}, {rect: [1, 1, 5, 5], color: brand}]\n"))
        self.assertEqual(shots.shots[0].highlights[0].color, (0.0, 0.0, 255.0))
        self.assertEqual(shots.shots[0].highlights[1].color, (0.0, 255.0, 0.0))
        self.assertIn("mark", style.palette)


class TestCamera(unittest.TestCase):

    def test_zoom_interpolates_in_log_scale(self) -> None:
        """Camera.at half way between two keys at zoom 1 and 4 gives zoom 2 (log scale) and the centre half way."""
        cam = Camera.resolve([CameraSpec(t=0, center=(0, 0), zoom=1), CameraSpec(t=2, center=(100, 50), zoom=4)],
                             (0, 0, 200, 100), (W, H))
        k = cam.at(1.0)
        self.assertAlmostEqual(k.zoom, 2.0, places=6)
        self.assertEqual(k.center, (50.0, 25.0))

    def test_rect_fits_and_fields_carry_over(self) -> None:
        """Camera.resolve centres a `rect` key's rect and fits it in 0.92 of the frame (with fill, a picture shot
        covers the frame); a later key without a field keeps it."""
        cam = Camera.resolve([CameraSpec(t=0, rect=(100, 100, 160, 45), yaw=5), CameraSpec(t=1, zoom=3)],
                             (0, 0, 640, 360), (W, H))
        self.assertEqual(cam.keys[0].center, (180.0, 122.5))
        self.assertAlmostEqual(cam.keys[0].zoom, 0.92 * min(W / 160, H / 45))
        self.assertEqual((cam.keys[1].center, cam.keys[1].yaw), ((180.0, 122.5), 5))
        cover = Camera.resolve([CameraSpec(t=0, rect=(0, 0, 160, 45))], (0, 0, 640, 360), (W, H), fill=True)
        self.assertAlmostEqual(cover.keys[0].zoom, max(W / 160, H / 45))

    def test_camera_moves_through_inner_keys(self) -> None:
        """Camera.at on a move through three keys keeps moving at the middle key (no stop), and starts and ends
        at rest."""
        cam = Camera.resolve([CameraSpec(t=0, center=(0, 0), zoom=1), CameraSpec(t=1, center=(100, 0)),
                              CameraSpec(t=2, center=(300, 0))], (0, 0, 400, 100), (W, H))

        def speed(t: float) -> float:
            return (cam.at(t + 1e-3).center[0] - cam.at(t - 1e-3).center[0]) / 2e-3
        self.assertGreater(speed(1.0), 50)
        self.assertLess(speed(1e-3), 1)
        self.assertLess(speed(2 - 1e-3), 1)
        self.assertAlmostEqual(cam.at(1.0).center[0], 100.0)


class TestGrade(unittest.TestCase):

    def test_grade_darkens_and_tints(self) -> None:
        """page_edits.apply_grade maps white through gain and tint and leaves black black (the `grade` tone
        change of a dark film)."""
        from short_video_tool.screencast.model import Grade
        from short_video_tool.screencast.page_edits import apply_grade
        img = np.zeros((2, 2, 3), np.uint8)
        img[0, 0] = 255
        out = apply_grade(img, Grade(gamma=1.6, gain=0.62, tint=(0.92, 1.0, 1.12)))
        self.assertEqual(out[1, 1].tolist(), [0, 0, 0])
        b, g, r = out[0, 0].tolist()
        self.assertAlmostEqual(g, 255 * 0.62, delta=1)
        self.assertGreater(b, g)
        self.assertLess(r, g)


class TestTyping(unittest.TestCase):

    def test_reveal_blanks_untyped_glyphs(self) -> None:
        """TypingReveal finds the 10 glyphs; half way through the typing its frame shows the right part of the
        text line as the field background, and once typed the line as in the screenshot."""
        img = np.full((60, 400, 3), 250, np.uint8)
        for i in range(10):
            cv2.rectangle(img, (20 + 30 * i, 20), (36 + 30 * i, 40), (20, 20, 20), -1)
        tr = TypingReveal(img, Typing((10, 10, 380, 40), 0.0, 1.0, caret=False), 1.0)
        self.assertEqual(tr.glyphs, 10)
        half = tr.frame(img, 0.5)
        self.assertLess(half[25:35, 20:160].mean(), 200)          # first five glyphs shown
        self.assertEqual(int(half[20:40, 170:330].min()), 250)    # last five blanked
        self.assertTrue(np.array_equal(tr.frame(img, 1.0), img))


class TestAlign(unittest.TestCase):

    def test_ecc_aligns_a_shifted_copy(self) -> None:
        """pictures.align warps a copy shifted by (14, 6) px back onto the original and reports success: the
        aligned difference is under 0.2 of the unaligned one. Guards the ECC scale and inverse warp of a wipe."""
        rng = np.random.default_rng(3)
        base = cv2.GaussianBlur((rng.random((240, 320, 3)) * 255).astype(np.uint8), (0, 0), 4)
        base = cv2.normalize(base, None, 0, 255, cv2.NORM_MINMAX)
        moved = cv2.warpAffine(base, np.float32([[1, 0, 14], [0, 1, 6]]), (320, 240), borderMode=cv2.BORDER_REFLECT)
        aligned, ok = pictures.align(base, moved)
        self.assertTrue(ok)
        inner = (slice(30, 210), slice(40, 280))
        before = np.abs(base[inner].astype(float) - moved[inner]).mean()
        after = np.abs(base[inner].astype(float) - aligned[inner]).mean()
        self.assertLess(after, before * 0.2)


class TestFrames(ProjectCase):

    def test_camera_zoom_moves_content(self) -> None:
        """Timeline.frames of a camera zooming onto the red dot moves it to the frame centre and enlarges it, and
        a zoom past the source warns to capture the page at 2x."""
        page(self.dir / "p.png")
        tl = self.timeline("shots:\n  - image: p.png\n    length: 1\n    camera:\n"
                           "      - {t: 0, rect: [0, 0, 640, 360]}\n      - {t: 1, center: [480, 120], zoom: 2}\n")
        x0, y0, n0 = red_centroid(self.frame(tl, 0.0))
        x1, y1, n1 = red_centroid(self.frame(tl, 0.99))
        self.assertGreater(math.hypot(x0 - W / 2, y0 - H / 2), 40)
        self.assertLess(math.hypot(x1 - W / 2, y1 - H / 2), 4)
        self.assertGreater(n1, n0 * 4)
        self.assertTrue(any("past the source" in w and "capture the page at 2x" in w for w in self.warnings))

    def test_upscale_keeps_page_coordinates(self) -> None:
        """Timeline.frames with `upscale` keeps page coordinates in the given picture's px over `scale`: centring
        on the red dot puts it in the frame centre whatever the upscale."""
        page(self.dir / "p.png")
        for up in ("", "    upscale: 1600\n"):
            tl = self.timeline("shots:\n  - image: p.png\n    scale: 1\n" + up + "    length: 1\n"
                               "    camera: [{t: 0, center: [480, 120], zoom: 1}]\n")
            x, y, _ = red_centroid(self.frame(tl, 0.5))
            self.assertLess(math.hypot(x - W / 2, y - H / 2), 2, up)

    def test_legibility_warning(self) -> None:
        """Timeline warns about a shot with a highlight whose camera never reaches 1.4 screen px per page px; at
        2x capture a zoom past the source asks for a larger rect, not a 2x capture."""
        page(self.dir / "p.png")
        self.timeline("shots:\n  - image: p.png\n    length: 1\n    highlights: [{rect: [40, 200, 160, 60]}]\n")
        self.assertTrue(any("UI text is unreadable" in w for w in self.warnings))
        self.warnings.clear()
        self.timeline("shots:\n  - image: p.png\n    scale: 2\n    length: 1\n    camera: [{t: 0, zoom: 4}]\n")
        self.assertTrue(any("frame a larger rect" in w for w in self.warnings), self.warnings)

    def test_vignette_spares_the_panel(self) -> None:
        """Timeline.frames applies the `vignette` to the backdrop only: a white page held flat stays white at its
        corners."""
        cv2.imwrite(str(self.dir / "w.png"), np.full((360, 640, 3), 255, np.uint8))
        tl = self.timeline("style: {vignette: 0.5}\nshots:\n  - image: w.png\n    length: 1\n"
                           "    camera: [{t: 0, center: [320, 180], zoom: 1}]\n")
        self.assertGreater(int(self.frame(tl, 0.5)[30, 30].min()), 245)

    def test_crossfade_blends_two_shots(self) -> None:
        """Timeline.frames half way through a 0.4 s `fade` from a red picture to a blue one holds both; before
        and after it, only one."""
        solid(self.dir / "r.png", (0, 0, 255))
        solid(self.dir / "b.png", (255, 0, 0))
        tl = self.timeline("style: {vignette: 0}\nfade: 0.4\nshots:\n"
                           "  - {type: picture, image: r.png, length: 1}\n"
                           "  - {type: picture, image: b.png, length: 1}\n")
        mid = self.frame(tl, 1.2)[H // 2, W // 2].astype(int)
        self.assertTrue(90 < mid[0] < 165 and 90 < mid[2] < 165, mid)
        self.assertLess(int(self.frame(tl, 0.9)[H // 2, W // 2][0]), 10)
        self.assertLess(int(self.frame(tl, 1.6)[H // 2, W // 2][2]), 10)

    def test_wipe_shows_aligned_halves(self) -> None:
        """Timeline.frames of a `wipe` between a picture and its shifted copy aligns the copy: right of the
        divider the after picture shows the dot where the before picture has it."""
        before = np.full((180, 320, 3), 200, np.uint8)
        cv2.circle(before, (240, 90), 20, (0, 0, 255), -1)
        cv2.rectangle(before, (20, 20), (120, 160), (40, 120, 40), -1)
        cv2.imwrite(str(self.dir / "a.png"), before)
        cv2.imwrite(str(self.dir / "b.png"), cv2.warpAffine(before, np.float32([[1, 0, 9], [0, 1, 5]]), (320, 180),
                                                            borderMode=cv2.BORDER_REPLICATE))
        tl = self.timeline("style: {vignette: 0}\nshots:\n  - type: picture\n    length: 1\n"
                           "    wipe: {before: a.png, after: b.png, divider: [[0, 160]]}\n")
        x, y, _ = red_centroid(self.frame(tl, 0.5))
        self.assertLess(math.hypot(x - 240, y - 90), 1.5)


if __name__ == "__main__":
    unittest.main()
