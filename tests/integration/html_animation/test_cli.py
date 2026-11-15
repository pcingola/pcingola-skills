"""The html-animation CLI end to end through its wrapper, on each timing library: init, one chapter, build,
validate, still with a mark, stills, and the player's hit query in headless Chromium. The libraries and Chromium
come from the plugin data directory, downloaded on first use."""
from __future__ import annotations

import functools
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright

from html_animation_tool.browser import LAUNCH_ARGS, Browser

ROOT = Path(__file__).resolve().parents[3]
WRAPPER = ROOT / "plugins/media/skills/html-animation/scripts/html-animation.sh"
DATA = ROOT / "tests/data/html_animation"
BLUE = (0x20, 0x50, 0xD0)
RED = (255, 0, 0)
LIBS = ("gsap", "anime", "motion")


def run(*args: str | Path) -> dict:
    done = subprocess.run([str(WRAPPER), *map(str, args)], capture_output=True, text=True)
    assert done.returncode == 0, f"{args}: {done.stderr}{done.stdout}"
    return json.loads(done.stdout)


def near(px: tuple, colour: tuple, tol: int = 8) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(px, colour))


class TestCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folders = {}
        for lib in LIBS:
            folder = Path(cls._tmp.name) / lib
            run("init", folder, "--lib", lib, "--size", "1:1", "--title", f"Box {lib}")
            run("add-chapter", folder, "box", "--duration", "2")
            shutil.copyfile(DATA / "box.html", folder / "chapters" / "box.html")
            shutil.copyfile(DATA / f"{lib}.js", folder / "chapters" / "box.js")
            shutil.copyfile(DATA / "content.json", folder / "content.json")
            run("build", folder)
            cls.folders[lib] = folder

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_validate(self) -> None:
        """The built folder of each library validates."""
        for lib, folder in self.folders.items():
            with self.subTest(lib):
                self.assertEqual(run("validate", folder), {"ok": True, "errors": []})

    def test_still_frames_and_mark(self) -> None:
        """still renders at stage size; at t=0 the block has not arrived, at the chapter's end it shows in its
        finished place; the mark is red where drawn (the ring at the point's radius) and absent elsewhere."""
        for lib, folder in self.folders.items():
            with self.subTest(lib):
                start = Image.open(run("still", folder, "--at", "0")["png"]).convert("RGB")
                end_out = run("still", folder, "--at", "2", "--mark", "point:300,300",
                              "--out", folder / "marked.png")
                self.assertEqual(end_out["mark"], {"point": {"x": 300, "y": 300}})
                end = Image.open(end_out["png"]).convert("RGB")
                self.assertEqual(end.size, (1080, 1080))
                self.assertGreater(max(ImageStat.Stat(end).stddev), 10, "frame is blank")
                self.assertTrue(near(start.getpixel((750, 550)), (255, 255, 255)), start.getpixel((750, 550)))
                self.assertTrue(near(end.getpixel((750, 550)), BLUE), end.getpixel((750, 550)))
                self.assertEqual(end.getpixel((300 + 25, 300)), RED)
                self.assertEqual(end.getpixel((300, 300 - 25)), RED)
                self.assertNotEqual(end.getpixel((300, 300)), RED)
                rect = Image.open(run("still", folder, "--at", "2", "--mark", "rect:550,350,400,400",
                                      "--out", folder / "rect.png")["png"]).convert("RGB")
                self.assertEqual(rect.getpixel((552, 500)), RED)
                self.assertTrue(near(rect.getpixel((750, 550)), BLUE))

    def test_seek_is_exact(self) -> None:
        """Frames from one page seeking 2, 0.8, 0.3, 0 equal the frames of a fresh load at each time."""
        for lib, folder in self.folders.items():
            with self.subTest(lib):
                times = ["2", "0.8", "0.3", "0"]
                many = run("stills", folder, "--at", ",".join(times), "--outdir", folder / "many")["pngs"]
                for t, png in zip(times, many):
                    fresh = run("still", folder, "--at", t, "--out", folder / f"fresh{t}.png")["png"]
                    diff = ImageChops.difference(Image.open(png).convert("RGB"), Image.open(fresh).convert("RGB"))
                    self.assertIsNone(diff.getbbox(), f"t={t} differs")

    def test_hits(self) -> None:
        """HA.hits reports the ids under a point innermost first and the ids a rectangle intersects, without the
        chapter section; the hidden block at t=0 is not reported."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(Browser().executable()), args=LAUNCH_ARGS)
            try:
                for lib, folder in self.folders.items():
                    with self.subTest(lib):
                        page = browser.new_page(viewport={"width": 540, "height": 540})
                        page.goto((folder / "index.html").as_uri() + "?still&t=2")
                        page.evaluate("() => window.HA_READY")
                        self.assertEqual(page.evaluate("() => HA.hits({point: {x: 630, y: 430}})"),
                                         ["box-tag", "box-block", "box-bg"])
                        self.assertEqual(page.evaluate("() => HA.hits({rect: {x: 0, y: 0, w: 200, h: 120}})"),
                                         ["box-label", "box-bg"])
                        page.evaluate("() => HA.seek(0)")
                        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        self.assertEqual(page.evaluate("() => HA.hits({point: {x: 750, y: 550}})"), ["box-bg"])
                        page.close()
            finally:
                browser.close()

    def test_post_message(self) -> None:
        """In a sandboxed iframe served over HTTP, as the editor serves it, the player answers the postMessage
        protocol: ha:ready with the chapters, ha:time after ha:seek, ha:hits for ha:query. Standalone, it autoplays
        with its play bar. (A sandboxed iframe from file:// cannot load its scripts.)"""
        folder = self.folders["anime"]
        parent = folder.parent / "parent.html"
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(folder.parent))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        parent.write_text(
            '<iframe id="f" sandbox="allow-scripts" width="540" height="540" src="anime/index.html?t=2"></iframe>'
            "<script>window.got = []; window.addEventListener('message', e => window.got.push(e.data));</script>")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(Browser().executable()), args=LAUNCH_ARGS)
            try:
                page = browser.new_page()
                page.goto(base + "parent.html")
                page.wait_for_function("() => window.got.some(m => m.type === 'ha:ready')")
                ready = page.evaluate("() => window.got.find(m => m.type === 'ha:ready')")
                self.assertEqual((ready["width"], ready["duration"], ready["chapters"][0]["id"]), (1080, 2, "box"))
                page.evaluate("() => document.getElementById('f').contentWindow.postMessage({type: 'ha:seek', t: 1.5}, '*')")
                page.wait_for_function("() => window.got.some(m => m.type === 'ha:time' && m.t === 1.5)")
                page.evaluate("() => document.getElementById('f').contentWindow.postMessage("
                              "{type: 'ha:query', qid: 7, point: {x: 630, y: 430}}, '*')")
                page.wait_for_function("() => window.got.some(m => m.type === 'ha:hits')")
                hits = page.evaluate("() => window.got.find(m => m.type === 'ha:hits')")
                self.assertEqual((hits["qid"], hits["t"], hits["chapter"], hits["ids"][0]), (7, 1.5, "box", "box-tag"))

                page.goto((folder / "index.html").as_uri())
                page.wait_for_function("() => window.HA && HA.playing")
                self.assertTrue(page.evaluate("() => !!document.getElementById('ha-bar')"))
            finally:
                browser.close()
                server.shutdown()

    def test_scrub_bar(self) -> None:
        """Standalone, moving the scrub bar while playing pauses the player at the chosen time
        (SKILL.md: opened plain it plays from 0 with a play and scrub bar)."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(Browser().executable()), args=LAUNCH_ARGS)
            try:
                for lib, folder in self.folders.items():
                    with self.subTest(lib=lib):
                        page = browser.new_page()
                        page.goto((folder / "index.html").as_uri())
                        page.wait_for_function("() => window.HA && HA.playing")
                        page.evaluate("() => { const s = document.getElementById('ha-scrub'); s.value = '1.25';"
                                      " s.dispatchEvent(new Event('input')); }")
                        self.assertEqual(page.evaluate("() => [HA.playing, HA.time]"), [False, 1.25])
                        page.close()
            finally:
                browser.close()

    def test_snapshot(self) -> None:
        """snapshot through the wrapper prints the version it wrote."""
        folder = self.folders["gsap"]
        self.assertEqual(run("snapshot", folder)["version"], 1)
        self.assertTrue((folder / "v1" / "chapters" / "box.js").is_file())

    def test_errors(self) -> None:
        """A failing command exits non-zero with the error on stderr; still past the end is refused."""
        done = subprocess.run([str(WRAPPER), "still", str(self.folders["gsap"]), "--at", "9"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("past the end", done.stderr)
