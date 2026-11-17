"""The particle_text technique in the render browser: its page copied into a scaffolded silent scene, with
targets of short_video_tool.particle_text for other words (landscape, and portrait fitted to the width), seeked by
`stills` without a render (assets/techniques/particle_text/note.md; SKILL.md, Commands)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from short_video_tool import config, pages, scenes, settings, stills, storyboard
from short_video_tool.particle_text import ParticleText
from tests.integration.short_video.wrapper_env import NODE_DIR
from tests.prereq import requires

TECHNIQUE = config.SCRIPTS_DIR.parent / "assets" / "techniques" / "particle_text"
FONT = (config.SCRIPTS_DIR.parents[4] / "plugins/docs/skills/revealjs-slideshow/assets/reveal.js/dist/theme/fonts"
        / "source-sans-pro/source-sans-pro-semibold.ttf")
STORYBOARD = """# Particle text

Topic: A word formed by particles.

## word
Brief: Particles spiral in and lock into two lines of text, a caption follows.
Length: 6
"""


@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run plugins/media/skills/short-video/scripts/short-video.sh setup")
class TestParticleTextPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def make(self, name: str, text: ParticleText, swaps: list[tuple[str, str]] = (), video: str = "") -> Path:
        """A project `name` (with `video` settings) whose silent scene `word` plays the technique page with the
        targets `two` of `text`; `swaps` are further replacements in the page. Returns the project."""
        p = Path(self._tmp.name) / name
        p.mkdir()
        (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
        if video:
            (p / "settings.yaml").write_text(video, encoding="utf-8")
        settings.use_project(p)
        self.data = storyboard.load(p)
        sdir = scenes.scaffold(p, storyboard.scene_by_id(self.data, "word"), NODE_DIR)
        html = (TECHNIQUE / "index.html").read_text(encoding="utf-8")
        for a, b in [('"particle_text"', '"word"'), ('const NAME = "title"', 'const NAME = "two"'),
                     ("title_targets.js", "two_targets.js"),
                     ('"tex-title" class="tex" src="title_tex.png"', '"tex-two" class="tex" src="two_tex.png"'), *swaps]:
            self.assertIn(a, html)
            html = html.replace(a, b)
        (sdir / "index.html").write_text(html, encoding="utf-8")
        text.write("two", sdir)
        return p

    def stills_at(self, project: Path, times: list[float]) -> list[np.ndarray]:
        scene = storyboard.scene_by_id(self.data, "word")
        pages.check(project, self.data, scene, NODE_DIR)
        page = pages.scene_page(project, self.data, scene)
        return [np.asarray(Image.open(p).convert("L"), dtype=np.float64)
                for p in stills.stills("word", page, times, NODE_DIR)]

    def test_stills(self) -> None:
        """The page passes the static checks of `render`; its frame 0 shows the particle spirals (the compile and
        double draw at load), and at 5.6 s the text block is lit at the frame centre with both lines, above a
        caption, while the corners stay dark. Guards the technique page, kit/particles.js and the command's files
        working together in the render browser."""
        project = self.make("landscape", ParticleText(("Two", "lines"), FONT, size=200, count=12000))
        first, last = self.stills_at(project, [0.0, 5.6])
        self.assertGreater((first > 120).mean(), 0.01)
        H, W = last.shape
        top, bottom = last[int(H * 0.25):int(H * 0.42), int(W * 0.4):int(W * 0.6)], last[int(H * 0.45):int(H * 0.6), int(W * 0.4):int(W * 0.6)]
        self.assertGreater((top > 180).mean(), 0.1)
        self.assertGreater((bottom > 180).mean(), 0.1)
        self.assertLess(last[:60, :60].mean(), 40)
        self.assertGreater((last[int(H * 0.68):int(H * 0.82), int(W * 0.3):int(W * 0.7)] > 180).mean(), 0.003)

    def test_portrait(self) -> None:
        """The page on a 1080x1920 frame with targets fitted to 75% of its width: at 5.6 s a long caption scales
        down to stay inside 80% of the frame width (no lit caption pixel in the outer 8% on either side) while the
        text block is lit at the centre. Guards the portrait section of note.md and pin's maxWidth."""
        swaps = [("width=1920, height=1080", "width=1080, height=1920"),
                 ("width: 1920px; height: 1080px", "width: 1080px; height: 1920px"),
                 ('data-width="1920" data-height="1080"', 'data-width="1080" data-height="1920"'),
                 ("A caption line under the word", "A much longer caption line under the word for a phone")]
        text = ParticleText(("Particle", "text block"), FONT, count=12000, width=1080, height=1920).fitted(0.75)
        project = self.make("portrait", text, swaps, "video:\n  width: 1080\n  height: 1920\n  fps: 30\n")
        [last] = self.stills_at(project, [5.6])
        H, W = last.shape
        self.assertEqual((W, H), (1080, 1920))
        self.assertGreater((last[int(H * 0.37):int(H * 0.55), int(W * 0.3):int(W * 0.7)] > 180).mean(), 0.1)
        band = last[int(H * 0.58):int(H * 0.62)]
        lit = np.nonzero((band > 200).any(axis=0))[0]
        self.assertGreater(len(lit), W * 0.3)
        self.assertGreater(lit.min(), W * 0.08)
        self.assertLess(lit.max(), W * 0.92)
