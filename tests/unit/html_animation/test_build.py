"""build: index.html from animation.json, content.json and the chapters."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from html_animation_tool.builder import Builder
from html_animation_tool.common import HAError
from html_animation_tool.enums import TimingLib
from html_animation_tool.project import Project

from tests.unit.html_animation.fixture import box_project


class TestBuild(unittest.TestCase):
    def test_index(self) -> None:
        """index.html holds the chapter inline in its section, HA_CONFIG with content, and scripts in the order
        libraries, player, chapters, start; script URLs carry a content hash."""
        with tempfile.TemporaryDirectory() as tmp:
            p = box_project(Path(tmp) / "a")
            html = p.index_html.read_text()
            self.assertIn('<section id="ch-box" class="ha-chapter" data-chapter="box">', html)
            self.assertIn('id="box-block"', html)
            self.assertIn('<div id="ha-stage" style="width: 1080px; height: 1080px;">', html)
            config = json.loads(re.search(r"window\.HA_CONFIG = (.*);</script>", html).group(1))
            self.assertEqual(config["content"]["label"], "Seek test")
            self.assertEqual([c["id"] for c in config["chapters"]], ["box"])
            srcs = re.findall(r'<script src="([^"?]+)\?v=[0-9a-f]{12}">', html)
            self.assertEqual(srcs, ["lib/gsap.min.js", "player.js", "chapters/box.js"])
            self.assertLess(html.index("chapters/box.js"), html.index("HA.start();"))
            self.assertTrue(Builder(p).current())

    def test_stale(self) -> None:
        """A changed source makes index.html stale until the next build; the script hash changes."""
        with tempfile.TemporaryDirectory() as tmp:
            p = box_project(Path(tmp) / "a")
            before = p.index_html.read_text()
            p.chapter_js("box").write_text(p.chapter_js("box").read_text() + "\n")
            self.assertFalse(Builder(p).current())
            Builder(p).build()
            self.assertNotEqual(before, p.index_html.read_text())
            self.assertTrue(Builder(p).current())

    def test_escapes_script_end(self) -> None:
        """Content with </script> cannot end the config script."""
        with tempfile.TemporaryDirectory() as tmp:
            p = box_project(Path(tmp) / "a", build=False)
            p.content_json.write_text(json.dumps({"label": "</script><b>", "color": "#000"}))
            Builder(p).build()
            self.assertNotIn("</script><b>", p.index_html.read_text())

    def test_refusals(self) -> None:
        """build refuses a folder with no chapters and a chapter with a missing file."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Project(Path(tmp) / "a")
            p.init(TimingLib.GSAP)
            with self.assertRaises(HAError):
                Builder(p).build()
            p.add_chapter("intro", 1)
            p.chapter_html("intro").unlink()
            with self.assertRaises(HAError):
                Builder(p).build()
