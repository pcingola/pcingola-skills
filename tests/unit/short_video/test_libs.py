"""short_video_tool.scenes: the pinned library files (`LIBS`), their hash check, the copy of the library and kit
files a page names in a `<script src>`, and the check that HyperFrames can seek the page."""
import json
import tempfile
import unittest
from pathlib import Path

from short_video_tool import scenes, settings

TIMING = {"duration": 2.0, "sentences": [{"index": 1, "text": "Hi.", "start": 0.2, "end": 0.6,
                                          "words": [{"text": "Hi.", "start": 0.2, "end": 0.6}]}]}


def _node_dir(tmp: str) -> Path:
    """A node directory holding a stub of every LIBS file; each stub's content is its file name."""
    node_dir = Path(tmp, "node")
    for name, lib in scenes.LIBS.items():
        (node_dir / lib.rel).parent.mkdir(parents=True, exist_ok=True)
        (node_dir / lib.rel).write_text(name, encoding="utf-8")
    return node_dir


def _kit_dir(tmp: str) -> Path:
    kit = Path(tmp, "kit")
    kit.mkdir()
    for name in ("camera.js", "glow.js"):
        (kit / name).write_text(name, encoding="utf-8")
    return kit


class TestLibs(unittest.TestCase):

    def test_lib_failures(self) -> None:
        """scenes.lib_failures names every missing file, then every file whose SHA-256 differs from its pin.
        Guards setup accepting a node_modules with a changed library."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp, "empty")
            failures = scenes.lib_failures(empty)
            self.assertEqual(len(failures), len(scenes.LIBS))
            self.assertTrue(all("missing" in f for f in failures))
            node_dir = _node_dir(tmp)
            failures = scenes.lib_failures(node_dir)
            self.assertEqual(len(failures), len(scenes.LIBS))
            self.assertTrue(all("SHA-256 differs" in f for f in failures))


PAGE = """<!doctype html><html><head>
<script src="gsap.min.js"></script>
<script src="./three.min.js"></script>
<script defer src='kit/camera.js'></script>
<script src="timing.js"></script>
<script src="mine.js"></script>
<script src="kit/sub/x.js"></script>
</head><body><div id="root" data-composition-id="s"></div></body></html>"""


class TestCopyByReference(unittest.TestCase):

    def test_page_files(self) -> None:
        """scenes.page_files maps the LIBS files and kit/<file>.js a page loads to their sources and leaves out
        timing.js, the author's files and paths below kit/. Guards copying only what the page names."""
        with tempfile.TemporaryDirectory() as tmp:
            node_dir, kit = _node_dir(tmp), _kit_dir(tmp)
            files = scenes.page_files(PAGE, node_dir, kit)
            self.assertEqual(files, {"gsap.min.js": node_dir / scenes.GSAP_REL,
                                     "three.min.js": node_dir / scenes.LIBS["three.min.js"].rel,
                                     "kit/camera.js": kit / "camera.js"})

    def test_copy_and_missing_only(self) -> None:
        """scenes.copy_page_files copies gsap.min.js always plus the named files (kit files into kit/); with
        missing_only it keeps a file the directory holds and adds the ones it lacks. Guards a
        `<script src="three.min.js">` added after scaffold."""
        with tempfile.TemporaryDirectory() as tmp:
            node_dir, kit = _node_dir(tmp), _kit_dir(tmp)
            out = Path(tmp, "v1")
            out.mkdir()
            plain = '<div id="root" data-composition-id="s"></div>'
            self.assertEqual(scenes.copy_page_files(out, plain, node_dir, kit_dir=kit), ["gsap.min.js"])
            self.assertFalse((out / "three.min.js").exists())
            (out / "gsap.min.js").write_text("kept", encoding="utf-8")
            copied = scenes.copy_page_files(out, PAGE, node_dir, missing_only=True, kit_dir=kit)
            self.assertEqual(sorted(copied), ["kit/camera.js", "three.min.js"])
            self.assertEqual((out / "gsap.min.js").read_text(), "kept")
            self.assertEqual((out / "three.min.js").read_text(), "three.min.js")
            self.assertEqual((out / "kit" / "camera.js").read_text(), "camera.js")

    def test_missing_source(self) -> None:
        """scenes.copy_page_files raises SceneError for a kit file the kit lacks (naming the kit's files) and for
        a library setup has not installed. Guards a page that would render without its script."""
        with tempfile.TemporaryDirectory() as tmp:
            node_dir, kit = _node_dir(tmp), _kit_dir(tmp)
            out = Path(tmp, "v1")
            out.mkdir()
            with self.assertRaisesRegex(scenes.SceneError, "camera.js, glow.js"):
                scenes.copy_page_files(out, '<script src="kit/nope.js"></script>', node_dir, kit_dir=kit)
            (node_dir / scenes.LIBS["d3.min.js"].rel).unlink()
            with self.assertRaisesRegex(scenes.SceneError, "setup"):
                scenes.copy_page_files(out, '<script src="d3.min.js"></script>', node_dir, kit_dir=kit)

    def test_shipped_kit(self) -> None:
        """Each file of assets/kit/ maps from kit/<file>.js with the default kit directory. Guards the kit path."""
        kit = settings.ASSETS_DIR / scenes.KIT
        names = sorted(f.name for f in kit.glob("*.js"))
        self.assertIn("camera.js", names)
        html = "".join(f'<script src="kit/{n}"></script>' for n in names)
        self.assertEqual(scenes.page_files(html, Path("/nonexistent")), {f"kit/{n}": kit / n for n in names})

    def test_scaffold_copies_by_reference(self) -> None:
        """scenes.scaffold copies gsap.min.js into a first version, and into the next version each LIBS and kit
        file the previous page names. Guards a page keeping its libraries across versions."""
        with tempfile.TemporaryDirectory() as tmp:
            project, node_dir = Path(tmp, "p"), _node_dir(tmp)
            voice = project / "voice" / "s" / "v1"
            voice.mkdir(parents=True)
            (voice / "timing.json").write_text(json.dumps(TIMING), encoding="utf-8")
            (voice / "meta.json").write_text("{}", encoding="utf-8")
            scene = {"id": "s", "brief": "A cube turns.", "beats": ["cube"]}
            first = scenes.scaffold(project, scene, node_dir)
            self.assertEqual(sorted(f.name for f in first.glob("*.js")), ["gsap.min.js", "timing.js"])
            html = (first / "index.html").read_text(encoding="utf-8")
            (first / "index.html").write_text(html.replace(
                '<script src="timing.js"></script>',
                '<script src="anime.umd.min.js"></script><script src="three.min.js"></script>'
                '<script src="kit/glow.js"></script><script src="timing.js"></script>'), encoding="utf-8")
            second = scenes.scaffold(project, scene, node_dir)
            for rel in ("gsap.min.js", "anime.umd.min.js", "three.min.js"):
                self.assertTrue((second / rel).is_file(), rel)
            self.assertEqual((second / "kit" / "glow.js").read_bytes(),
                             (settings.ASSETS_DIR / "kit" / "glow.js").read_bytes())
            self.assertFalse((second / "motion.js").exists())


ROOT = '<div id="root" data-composition-id="s1" data-start="0"{extra}>'


class TestCheckTimeline(unittest.TestCase):

    def test_cases(self) -> None:
        """scenes.check_timeline accepts a registered GSAP timeline or an hf-seek listener, refuses a page with
        neither or a registration under another id, and needs the listener on a data-no-timeline root. Guards
        render refusing a page HyperFrames would show frozen."""
        gsap = '<script>window.__timelines["s1"] = tl;</script>'
        other = '<script>window.__timelines["s2"] = tl;</script>'
        seek = '<script>window.addEventListener("hf-seek", e => tl.seek(e.detail.time * 1000));</script>'
        plain, no_tl = ROOT.format(extra=""), ROOT.format(extra=" data-no-timeline")
        self.assertEqual(scenes.check_timeline(plain + gsap), [])
        self.assertEqual(scenes.check_timeline(plain + seek), [])
        self.assertEqual(scenes.check_timeline(no_tl + seek), [])
        self.assertEqual(len(scenes.check_timeline(plain)), 1)
        self.assertEqual(len(scenes.check_timeline(plain + other)), 1)
        self.assertIn("hf-seek", scenes.check_timeline(no_tl + gsap)[0])
        self.assertEqual(scenes.check_timeline("<div></div>"), ["no element with data-composition-id"])

    def test_starting_pages_pass(self) -> None:
        """Every starting page in assets/ passes the check once filled. Guards scaffold output render accepts."""
        for kind in ("scene", "scene-drawn", "world", "title", "summary", "end"):
            self.assertEqual(scenes.check_timeline(scenes.render_template("s1", 2.0, kind)), [], kind)


if __name__ == "__main__":
    unittest.main()
