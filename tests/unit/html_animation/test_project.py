"""The project format: animation.json checks, init, add-chapter, snapshot and the mark spec."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from html_animation_tool.animation import Animation
from html_animation_tool.common import PLAYER, HAError
from html_animation_tool.enums import ExtraLib, Size, TimingLib
from html_animation_tool.mark import Mark
from html_animation_tool.project import Project

from tests.unit.html_animation.fixture import box_project

VALID = {"title": "T", "size": "16:9", "width": 1920, "height": 1080, "fps": 30, "lib": "gsap",
         "chapters": [{"id": "intro", "title": "Intro", "duration": 2.5}]}


class TestAnimationJson(unittest.TestCase):
    def test_valid(self) -> None:
        """A complete animation.json has no problems and round-trips through Animation."""
        self.assertEqual(Animation.problems(VALID), [])
        self.assertEqual(Animation.from_dict(VALID).to_dict(), VALID)

    def test_each_problem(self) -> None:
        """Each malformed field is reported. Guards validate's format rule."""
        cases = {
            "unknown key 'extra'": {**VALID, "extra": 1},
            "missing key 'fps'": {k: v for k, v in VALID.items() if k != "fps"},
            "size must be one of": {**VALID, "size": "3:2"},
            "width and height must be 1080 and 1920": {**VALID, "size": "9:16"},
            "fps must be an integer": {**VALID, "fps": 0},
            "lib must be one of": {**VALID, "lib": "jquery"},
            "id must match": {**VALID, "chapters": [{"id": "Intro", "duration": 1}]},
            "duplicate id": {**VALID, "chapters": [{"id": "a", "duration": 1}, {"id": "a", "duration": 1}]},
            "duration must be a number": {**VALID, "chapters": [{"id": "a", "duration": 0}]},
        }
        for expected, data in cases.items():
            with self.subTest(expected):
                problems = Animation.problems(data)
                self.assertTrue(any(expected in p for p in problems), problems)
                with self.assertRaises(HAError):
                    Animation.from_dict(data)

    def test_sizes(self) -> None:
        self.assertEqual(Size("4:5").pixels, (1080, 1350))
        self.assertEqual(Size("9:16").pixels, (1080, 1920))


class TestInit(unittest.TestCase):
    def test_init_files(self) -> None:
        """init writes player.js, the pinned libraries, animation.json without chapters and content.json {}."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Project(Path(tmp) / "anim")
            out = p.init(TimingLib.ANIME, Size.TALL, "Tall", (ExtraLib.D3,))
            self.assertTrue(out["created"])
            self.assertEqual(out["libs"], ["anime", "d3"])
            self.assertEqual(p.player_js.read_bytes(), PLAYER.read_bytes())
            data = json.loads(p.animation_json.read_text())
            self.assertEqual((data["width"], data["height"], data["lib"], data["chapters"]), (1080, 1920, "anime", []))
            self.assertEqual(json.loads(p.content_json.read_text()), {})

    def test_init_again_keeps_content(self) -> None:
        """init on an existing folder restores player.js and adds libraries; it keeps content and refuses
        another timing library."""
        with tempfile.TemporaryDirectory() as tmp:
            p = box_project(Path(tmp) / "anim")
            p.player_js.write_text("changed")
            out = p.init(TimingLib.GSAP, extras=(ExtraLib.THREE,))
            self.assertFalse(out["created"])
            self.assertEqual(out["libs"], ["gsap", "three"])
            self.assertEqual(p.player_js.read_bytes(), PLAYER.read_bytes())
            self.assertEqual([c.id for c in p.load().chapters], ["box"])
            self.assertEqual(p.content()["label"], "Seek test")
            with self.assertRaises(HAError):
                p.init(TimingLib.MOTION)


class TestAddChapter(unittest.TestCase):
    def test_stub_per_library(self) -> None:
        """add-chapter appends the chapter and writes a stub that calls HA.chapter with its id and returns the
        library's paused timeline."""
        calls = {"gsap": "gsap.timeline({ paused: true })", "anime": "anime.createTimeline({ autoplay: false })",
                 "motion": "Motion.animate(sequence)"}
        with tempfile.TemporaryDirectory() as tmp:
            for lib, call in calls.items():
                p = Project(Path(tmp) / lib)
                p.init(TimingLib(lib))
                p.add_chapter("intro", 2)
                out = p.add_chapter("outro", 1.5, "End")
                self.assertEqual(out["start"], 2)
                self.assertEqual([(c.id, c.title, c.duration) for c in p.load().chapters],
                                 [("intro", "intro", 2), ("outro", "End", 1.5)])
                js = p.chapter_js("outro").read_text()
                self.assertIn('HA.chapter("outro"', js)
                self.assertIn(call, js)
                self.assertEqual(p.chapter_html("outro").read_text(), "")

    def test_refusals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Project(Path(tmp) / "a")
            p.init(TimingLib.GSAP)
            p.add_chapter("intro", 2)
            for cid, duration in (("intro", 1), ("Bad", 1), ("x", 0)):
                with self.subTest(cid), self.assertRaises(HAError):
                    p.add_chapter(cid, duration)


class TestSnapshot(unittest.TestCase):
    def test_versions(self) -> None:
        """snapshot copies animation.json, content.json and chapters/ into v1, v2, ..."""
        with tempfile.TemporaryDirectory() as tmp:
            p = box_project(Path(tmp) / "a", build=False)
            self.assertEqual(p.snapshot()["version"], 1)
            p.content_json.write_text('{"label": "x", "color": "#000"}')
            self.assertEqual(p.snapshot()["version"], 2)
            self.assertEqual(json.loads((p.folder / "v1" / "content.json").read_text())["label"], "Seek test")
            self.assertEqual(json.loads((p.folder / "v2" / "content.json").read_text())["label"], "x")
            self.assertTrue((p.folder / "v2" / "chapters" / "box.js").is_file())
            self.assertFalse((p.folder / "v2" / "lib").exists())


class TestMark(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(Mark.parse("point:10,20.5").to_dict(), {"point": {"x": 10, "y": 20.5}})
        self.assertEqual(Mark.parse("rect:1,2,30,40").to_dict(), {"rect": {"x": 1, "y": 2, "w": 30, "h": 40}})
        for bad in ("point:1", "rect:1,2,0,4", "circle:1,2", "point:a,b"):
            with self.subTest(bad), self.assertRaises(HAError):
                Mark.parse(bad)
