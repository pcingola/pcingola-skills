"""Integration test for short_video_tool.mix.assemble with real FFmpeg.

Two scenes are generated with FFmpeg lavfi: a colour video plus a 440 Hz
"voice" that is on for 1.5 s and off for 1.5 s. The music is a 220 Hz tone
shorter than the film, so it has to loop. The project around them is built
the way `voice` and `render` leave it (with meta.json), so `assemble` finds
the rendered versions as it does in a real project.
"""
import hashlib
import json
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import brand, credit, media, mix, music, settings, state, storyboard, versions
from tests.unit.short_video.pngs import solid_png
from tests.prereq import requires

FPS = 30
SR = 48000
SCENES = {"one": 6.0, "two": 4.5}
VOICE_HZ = 440
MUSIC_HZ = 220


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _goertzel(samples: list[float], freq: float) -> float:
    """Amplitude of one frequency in a block of samples."""
    n = len(samples)
    k = round(n * freq / SR)
    w = 2 * math.pi * k / n
    coeff = 2 * math.cos(w)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x + coeff * s1 - s2
        s2, s1 = s1, s0
    power = s1 * s1 + s2 * s2 - coeff * s1 * s2
    return 2 * math.sqrt(max(power, 0.0)) / n


SETTINGS = "author: [Jane O'Doe]\nmusic: {file: music.wav}\n"


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed (brew install ffmpeg)")
class TestAssemble(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "film_project"
        for d in ("images", "sources", "voice", "scenes", "music", "film"):
            (p / d).mkdir(parents=True)
        _ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=64x36", "-frames:v", "1", str(p / "images" / "a.png"))

        scene_md = "".join(f"\n## {sid}\nImage: a.png\nBrief: Nothing moves.\n\n"
                           "| Narration | On screen |\n|---|---|\n| Beep. | hold |\n" for sid in SCENES)
        (p / "storyboard.md").write_text("# Test film\n\nTopic: Tones.\n" + scene_md, encoding="utf-8")
        (p / "settings.yaml").write_text(SETTINGS, encoding="utf-8")
        settings.use_project(p)
        cls.data = storyboard.load(p)

        for scene in storyboard.scenes(cls.data):
            sid, dur = scene["id"], SCENES[scene["id"]]
            vdir = versions.next_version(state.voice_root(p, sid))
            state.write_meta(vdir, {"duration": dur})
            sdir = versions.next_version(state.scene_root(p, sid))
            (sdir / "index.html").write_text("<html></html>")
            tone = f"0.5*sin(2*PI*{VOICE_HZ}*t)*lt(mod(t\\,3)\\,1.5)"
            _ffmpeg(
                "-f", "lavfi", "-i", f"color=c=blue:s=320x180:r={FPS}:d={dur}",
                "-f", "lavfi", "-i", f"aevalsrc={tone}:s=24000:d={dur}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-shortest", str(sdir / "scene.mp4"),
            )
            state.write_meta(sdir, {"voice_version": vdir.name})

        tone_file = p / "music.wav"
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency={MUSIC_HZ}:sample_rate=44100:duration=3",
                "-ac", "2", str(tone_file))
        music.import_file(p, tone_file)

        cls.film = mix.assemble(p, cls.data)

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def _samples(self, start: float, length: float) -> list[float]:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(length), "-i", str(self.film),
             "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
            check=True, capture_output=True,
        ).stdout
        return [x / 32768 for x in struct.unpack(f"<{len(raw) // 2}h", raw)]

    def test_output_path_and_manifest(self) -> None:
        """mix.assemble writes film/v1/film.mp4 and a manifest with each scene's scene and voice version and the
        music version and gain. Guards the manifest film_sources and the agent read."""
        self.assertEqual(self.film, self.project / "film" / "v1" / "film.mp4")
        manifest = json.loads((self.film.parent / "manifest.json").read_text())
        self.assertEqual([s["id"] for s in manifest["scenes"]], ["one", "two"])
        self.assertEqual(manifest["scenes"][0]["scene_version"], "v1")
        self.assertEqual(manifest["scenes"][0]["voice_version"], "v1")
        self.assertEqual(manifest["music"]["version"], "v1")
        self.assertEqual(manifest["music"]["gain_db"], -14.0)

    def test_one_video_and_one_audio_stream(self) -> None:
        """mix.assemble gives one video and one audio stream at mix.sample_rate. Guards the -map of [v] and
        [aout] and the output sample rate."""
        streams = media.probe(self.film)["streams"]
        self.assertEqual(sorted(s["codec_type"] for s in streams), ["audio", "video"])
        audio = next(s for s in streams if s["codec_type"] == "audio")
        self.assertEqual(int(audio["sample_rate"]), 48000)

    def test_duration_is_sum_of_scenes(self) -> None:
        """mix.assemble gives a film and a video stream as long as the sum of the scenes. Guards each scene's
        voice fitted to its video length."""
        self.assertAlmostEqual(media.duration(self.film), sum(SCENES.values()), delta=1 / FPS)
        video = next(s for s in media.probe(self.film)["streams"] if s["codec_type"] == "video")
        self.assertAlmostEqual(float(video["duration"]), sum(SCENES.values()), delta=1 / FPS)

    def test_integrated_loudness(self) -> None:
        """mix.assemble's two-pass loudnorm lands the film within 1 LU of -16 LUFS. Guards the measured values
        being applied in the second pass."""
        err = subprocess.run(
            ["ffmpeg", "-nostats", "-i", str(self.film), "-map", "0:a", "-af", "ebur128", "-f", "null", "-"],
            capture_output=True, text=True,
        ).stderr
        summary = err[err.rindex("Summary:"):]
        lufs = float(summary.split("I:")[1].split("LUFS")[0])
        self.assertAlmostEqual(lufs, -16.0, delta=1.0)

    def test_music_ducked_during_voice(self) -> None:
        # Scene one, second cycle: voice on 3.0-4.5 s, off 4.5-6.0 s (past the 1 s fade-in).
        """mix.assemble ducks the music under the voice to below 0.6 of its level in the gaps. Guards the
        sidechaincompress keyed by the voice."""
        during = _goertzel(self._samples(3.4, 1.0), MUSIC_HZ)
        gap = _goertzel(self._samples(5.0, 0.9), MUSIC_HZ)
        self.assertGreater(gap, 0)
        self.assertLess(during, gap * 0.6, f"music during voice {during:.4f}, in gap {gap:.4f}")

    def test_music_loops_past_its_length(self) -> None:
        # The music file is 3 s long. In the gap after it ends (5.0-5.9 s) it must
        # be about as loud as in the gap before it ends (1.6-2.9 s, after the fade-in).
        """mix.assemble loops a 3 s music file to the film length. Guards -stream_loop -1 on the music input."""
        before_end = _goertzel(self._samples(1.6, 1.3), MUSIC_HZ)
        after_end = _goertzel(self._samples(5.0, 0.9), MUSIC_HZ)
        self.assertGreater(after_end, before_end * 0.5)

    def test_second_assemble_is_new_version(self) -> None:
        """A second mix.assemble writes film/v2 and leaves v1 unchanged. Guards never overwriting a film
        version."""
        before = hashlib.sha256(self.film.read_bytes()).digest()
        mtime = self.film.stat().st_mtime_ns
        film2 = mix.assemble(self.project, self.data)
        self.assertEqual(film2, self.project / "film" / "v2" / "film.mp4")
        self.assertEqual(hashlib.sha256(self.film.read_bytes()).digest(), before)
        self.assertEqual(self.film.stat().st_mtime_ns, mtime)

    def test_author_metadata(self) -> None:
        """mix.assemble writes the author as artist and copyright tags and in the manifest, with a quote in the
        name. Guards the metadata of the creator credit."""
        tags = media.probe(self.film)["format"]["tags"]
        self.assertEqual(tags["artist"], "Jane O'Doe")
        self.assertTrue(tags["copyright"].endswith(" Jane O'Doe"))
        manifest = json.loads((self.film.parent / "manifest.json").read_text())
        self.assertEqual(manifest["author"], "Jane O'Doe")

    def test_without_author(self) -> None:
        """mix.assemble of a project with an empty `author:` writes a film with no artist tag and author null in
        the manifest. Guards an empty "Made by" not stopping the film."""
        settings_file = self.project / "settings.yaml"
        settings_file.write_text("author: []\n", encoding="utf-8")
        settings.use_project(self.project)
        try:
            film = mix.assemble(self.project, self.data)
        finally:
            settings_file.write_text(SETTINGS, encoding="utf-8")
            settings.use_project(self.project)
        self.assertNotIn("artist", media.probe(film)["format"].get("tags", {}))
        self.assertIsNone(json.loads((film.parent / "manifest.json").read_text())["author"])

    def test_voice_only_without_music_settings(self) -> None:
        """mix.assemble without `music.file` writes a voice-only film with music null in the manifest and no
        music in the gaps. Guards the voice-only path."""
        settings_file = self.project / "settings.yaml"
        settings_file.write_text("author: [Jane O'Doe]\n", encoding="utf-8")
        settings.use_project(self.project)
        try:
            film = mix.assemble(self.project, self.data)
        finally:
            settings_file.write_text(SETTINGS, encoding="utf-8")
            settings.use_project(self.project)
        manifest = json.loads((film.parent / "manifest.json").read_text())
        self.assertIsNone(manifest["music"])
        self.assertAlmostEqual(media.duration(film), sum(SCENES.values()), delta=1 / FPS)
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "5.0", "-t", "0.9", "-i", str(film),
             "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
            check=True, capture_output=True,
        ).stdout
        gap = [x / 32768 for x in struct.unpack(f"<{len(raw) // 2}h", raw)]
        self.assertLess(_goertzel(gap, MUSIC_HZ), 1e-3)

    def test_uses_latest_rendered_version_and_refuses_without_one(self) -> None:
        """mix.assemble skips a scaffolded but unrendered version and refuses a scene with no rendered version,
        naming it. Guards state.latest_render requiring meta.json."""
        sdir = versions.next_version(state.scene_root(self.project, "two"))  # scaffolded, not rendered
        try:
            film = mix.assemble(self.project, self.data)
            manifest = json.loads((film.parent / "manifest.json").read_text())
            self.assertEqual(manifest["scenes"][1]["scene_version"], "v1")
        finally:
            sdir.rmdir()
        data = {**self.data, "scenes": [*self.data["scenes"], {"id": "three", "image": "a.png"}]}
        with self.assertRaises(mix.AssembleError) as cm:
            mix.assemble(self.project, data)
        self.assertIn("three", str(cm.exception))


def _bright_pixels(video: Path, t: float) -> int:
    """Near-white pixels in the bottom-right corner, where the caption goes."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
         "-vf", "crop=700:120:1220:960,format=gray", "-f", "rawvideo", "-"],
        check=True, capture_output=True,
    ).stdout
    return sum(1 for b in raw if b > 100)


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed (brew install ffmpeg)")
class TestCreditFile(unittest.TestCase):

    def test_caption_and_tags_added_audio_copied(self) -> None:
        """credit.credit_file draws a light caption on a dark video, writes the artist tag, keeps one audio
        stream and the length, with a colon and quote in the name, and refuses to overwrite its input. Guards
        drawtext from a textfile with expansion=none and the `credit` command."""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "old film.mp4"
            _ffmpeg("-f", "lavfi", "-i", f"color=c=blue:s=1920x1080:r={FPS}:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src))
            out = credit.credit_file(src, Path(d) / "out.mp4", "Jane O'Doe: 100%")
            self.assertEqual(_bright_pixels(src, 1.0), 0)
            self.assertGreater(_bright_pixels(out, 1.0), 300)  # light text on the dark blue corner
            info = media.probe(out)
            self.assertEqual(info["format"]["tags"]["artist"], "Jane O'Doe: 100%")
            audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
            self.assertEqual(len(audio), 1)
            self.assertAlmostEqual(media.duration(out), media.duration(src), delta=0.05)
            with self.assertRaises(media.ToolError):
                credit.credit_file(src, src, "Jane")

    def test_dark_caption_on_light_video(self) -> None:
        """credit.credit_file draws a dark caption on a light video, chosen from credit.corner_luma. Guards the
        caption colour per corner brightness."""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "light.mp4"
            _ffmpeg("-f", "lavfi", "-i", f"color=c=white:s=1920x1080:r={FPS}:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src))
            self.assertGreater(credit.corner_luma(src, [1.0]), 200)
            out = credit.credit_file(src, Path(d) / "out.mp4", "Jane Doe")
            raw = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(out), "-frames:v", "1",
                 "-vf", "crop=700:120:1220:960,format=gray", "-f", "rawvideo", "-"],
                check=True, capture_output=True,
            ).stdout
            self.assertGreater(sum(1 for b in raw if b < 180), 300)


GOLD = (0xE6, 0x9F, 0x00)  # the amber disc of the acme test brand
# The acme test brand (tests/brands), read in place as the brand skill reports a brand folder.
BRAND_SRC = Path(__file__).resolve().parents[2] / "brands/acme"


def _gold(video: Path, t: float, box: tuple[int, int, int, int],
          color: tuple[int, int, int] = GOLD) -> list[tuple[int, int, int]]:
    """Pixels close to `color` (default the brand gold) inside `box` (x, y, w, h) of the frame at `t`."""
    x, y, w, h = box
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
         "-vf", f"crop={w}:{h}:{x}:{y},format=rgb24", "-f", "rawvideo", "-"],
        check=True, capture_output=True,
    ).stdout
    px = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    return [q for q in px if all(abs(a - b) <= 40 for a, b in zip(q, color))]


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed (brew install ffmpeg)")
class TestBrandLogo(unittest.TestCase):
    """The caption logo of the acme test brand, read in place, on real frames."""

    def setUp(self) -> None:
        settings.use_project(None)
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.b = brand.load("acme", BRAND_SRC)
        png = brand.png_size(self.b["dir"] / self.b["raster"])
        self.box = credit.logo_box((1920, 1080), png, self.b["caption"])[:4]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _clip(self, name: str, color: str, dur: float) -> Path:
        out = self.d / name
        _ffmpeg("-f", "lavfi", "-i", f"color=c={color}:s=1920x1080:r={FPS}:d={dur}",
                "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out))
        return out

    def test_credit_file_logo_in_place_and_gold(self) -> None:
        """credit.credit_file with the acme test brand overlays the logo inside credit.logo_box in its colour and
        nowhere else in the corner, and draws no logo without a brand. Guards the logo position computed by
        logo_box matching what FFmpeg draws."""
        src = self._clip("in.mp4", "0x14234a", 2)
        w, h = self.box[2:]
        out = credit.credit_file(src, self.d / "brand.mp4", "Jane Doe", self.b)
        inside = _gold(out, 1.0, self.box)
        self.assertGreater(len(inside), w * h // 8)  # the symbol covers about a third of its box
        for i in range(3):  # mean colour of the solid logo pixels within encoding tolerance
            self.assertLess(abs(sum(q[i] for q in inside) / len(inside) - GOLD[i]), 20)
        # Nothing gold outside the box (plus 2 px for 4:2:0 chroma) in the bottom-right corner.
        corner = (1920 - 700, 1080 - 150, 700, 150)
        x, y, w, h = self.box
        self.assertEqual(len(_gold(out, 1.0, corner)), len(_gold(out, 1.0, (x - 2, y - 2, w + 4, h + 4))))
        plain = credit.credit_file(src, self.d / "plain.mp4", "Jane Doe")
        self.assertEqual(_gold(plain, 1.0, corner), [])

    def test_logo_only_on_captioned_scenes(self) -> None:
        """mix.mix with a brand draws the logo only on captioned scenes. Guards title and end scenes having no
        caption logo."""
        files = [self._clip("a.mp4", "0x14234a", 2), self._clip("b.mp4", "white", 2)]
        out = self.d / "film.mp4"
        mix.mix(files, None, out, -14.0, author="Jane Doe", captioned=[True, False], b=self.b)
        self.assertGreater(len(_gold(out, 1.0, self.box)), 0)
        self.assertEqual(_gold(out, 3.0, (1920 - 700, 1080 - 150, 700, 150)), [])


RED, GREEN = (255, 0, 0), (0, 200, 0)


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed (brew install ffmpeg)")
class TestLogoOnDark(unittest.TestCase):
    """`raster_on_dark` on dark scenes, `raster` on light ones, in one box."""

    def setUp(self) -> None:
        settings.use_project(None)
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        folder = self.d / "mine"
        folder.mkdir()
        solid_png(folder / "light.png", 40, 40, RED)
        solid_png(folder / "dark.png", 80, 80, GREEN)
        (folder / "brand.yaml").write_text("raster: light.png\nraster_on_dark: dark.png\n"
                                           "caption: {height: 1.3, gap: 0.45}\n")
        self.b = brand.load("mine", folder)
        x, y, w, h = credit.logo_box((1920, 1080), (40, 40), self.b["caption"])[:4]
        self.box = (x + 2, y + 2, w - 4, h - 4)  # inside, clear of chroma bleed at the edges

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _clip(self, name: str, color: str) -> Path:
        out = self.d / name
        _ffmpeg("-f", "lavfi", "-i", f"color=c={color}:s=1920x1080:r={FPS}:d=2",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out))
        return out

    def test_logo_per_scene_brightness(self) -> None:
        """mix.mix draws raster_on_dark on a dark scene and raster on a light one, filling the logo box. Guards
        the per-scene logo PNG in one film."""
        files = [self._clip("dark.mp4", "0x0f172a"), self._clip("light.mp4", "white")]
        out = self.d / "film.mp4"
        mix.mix(files, None, out, -14.0, author="Jane Doe", b=self.b)
        n = self.box[2] * self.box[3]
        self.assertEqual(len(_gold(out, 1.0, self.box, GREEN)), n)
        self.assertEqual(_gold(out, 1.0, self.box, RED), [])
        self.assertEqual(len(_gold(out, 3.0, self.box, RED)), n)
        self.assertEqual(_gold(out, 3.0, self.box, GREEN), [])

    def test_credit_file_picks_by_colour(self) -> None:
        """credit.credit_file picks raster_on_dark for a dark video and raster for a light one. Guards the logo
        choice in the `credit` command."""
        n = self.box[2] * self.box[3]
        dark = credit.credit_file(self._clip("dark.mp4", "0x0f172a"), self.d / "d.mp4", "Jane Doe", self.b)
        self.assertEqual(len(_gold(dark, 1.0, self.box, GREEN)), n)
        light = credit.credit_file(self._clip("light.mp4", "white"), self.d / "l.mp4", "Jane Doe", self.b)
        self.assertEqual(len(_gold(light, 1.0, self.box, RED)), n)


if __name__ == "__main__":
    unittest.main()
