"""short_video_tool.mix and credit: the film's filter graph and the creator caption."""
import tempfile
import unittest
from pathlib import Path

from short_video_tool import brand, cli, credit, mix, scenes, settings, storyboard
from tests.unit.short_video.pngs import solid_png

# The acme test brand (tests/brands), read in place as the brand skill reports a brand folder.
BRAND_SRC = Path(__file__).resolve().parents[2] / "brands/acme"


MEASURED = mix.Loudness("-23.40", "-4.10", "6.20", "-33.80", "0.35")


class TestFilterGraph(unittest.TestCase):

    def test_second_pass(self) -> None:
        """mix.build_filter_graph second pass: each scene's voice trimmed and padded to its video length, concat
        into the caption, music trimmed, faded and gained, sidechain ducking and the measured loudnorm values
        applied linearly. Guards the film's stage order and the voice staying in sync with the pictures."""
        stages = mix.build_filter_graph([20.0, 12.5], -14.0, MEASURED, caption="drawtext=x").split(";")
        self.assertEqual(stages[:4], [
            "[0:a:0]atrim=0:20,apad=whole_dur=20[a0]",
            "[1:a:0]atrim=0:12.5,apad=whole_dur=12.5[a1]",
            "[0:v:0][a0][1:v:0][a1]concat=n=2:v=1:a=1[vcat][voice_raw]",
            "[vcat]drawtext=x[v]",
        ])
        music = next(s for s in stages if s.startswith("[2:a:0]"))
        for part in ("atrim=0:32.5", "afade=t=in:st=0:d=1", "afade=t=out:st=29.5:d=3", "volume=-14dB"):
            self.assertIn(part, music)
        self.assertTrue(any(s.startswith("[music][key]sidechaincompress") for s in stages))
        self.assertIn("measured_I=-23.40", stages[-1])
        self.assertIn("offset=0.35:linear=true", stages[-1])

    def test_first_pass_and_short_film(self) -> None:
        """mix.build_filter_graph first pass of a 4 s film: audio-only concat, fades clamped to half the film
        and loudnorm in measure mode. Guards fades longer than a short film."""
        graph = mix.build_filter_graph([4.0], -20.5, video=False)
        self.assertIn("[a0]concat=n=1:v=0:a=1[voice_raw]", graph)
        self.assertIn("afade=t=out:st=2:d=2", graph)  # fades clamped to half the film
        self.assertIn("volume=-20.5dB", graph)
        self.assertIn("print_format=json", graph)
        self.assertNotIn("measured_I", graph)

    def test_voice_only(self) -> None:
        """mix.build_filter_graph with music_db None sends the voice straight to loudnorm with no music input,
        ducking or amix, and mix.ffmpeg_inputs adds no looped music input. Guards the voice-only film without
        `music.file`."""
        stages = mix.build_filter_graph([20.0, 12.5], None, MEASURED).split(";")
        self.assertEqual(stages[2], "[0:v:0][a0][1:v:0][a1]concat=n=2:v=1:a=1[v][voice_raw]")
        self.assertTrue(stages[-1].startswith("[voice_raw]aresample="))
        self.assertIn("measured_I=-23.40", stages[-1])
        self.assertTrue(stages[-1].endswith("[aout]"))
        self.assertFalse(any("[2:a:0]" in s or "sidechaincompress" in s or "amix" in s for s in stages))
        self.assertEqual(mix.ffmpeg_inputs([Path("a.mp4")], None), ["-i", "a.mp4"])

    def test_mix_values_come_from_project_settings(self) -> None:
        """mix.build_filter_graph reads fade and loudness values from the project's settings.yaml over the
        defaults. Guards settings being read at call time, not import time."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "settings.yaml").write_text("mix: {fade_in: 2.5, loudness_i: -14}\n")
            settings.use_project(Path(d))
            try:
                graph = mix.build_filter_graph([10.0], -14.0)
            finally:
                settings.use_project(None)
        self.assertIn("afade=t=in:st=0:d=2.5", graph)
        self.assertIn("loudnorm=I=-14:", graph)

    def test_parse_loudnorm(self) -> None:
        """mix.parse_loudnorm reads the first-pass JSON from FFmpeg stderr and raises AssembleError without it.
        Guards the two-pass loudnorm hand-off."""
        stderr = '[x]\n{\n "input_i" : "-27.61", "input_tp" : "-9.02", "input_lra" : "3.40",\n' \
                 ' "input_thresh" : "-37.89", "target_offset" : "0.01"\n}\n'
        self.assertEqual(mix.parse_loudnorm(stderr), mix.Loudness("-27.61", "-9.02", "3.40", "-37.89", "0.01"))
        with self.assertRaises(mix.AssembleError):
            mix.parse_loudnorm("no json here")

    def test_silent_mix_skips_normalisation(self) -> None:
        """mix.build_filter_graph second pass with a measured loudness of -inf (a film where no scene has sound)
        passes the audio through with no loudnorm. Guards assembling a silent film."""
        silent = mix.Loudness("-inf", "-inf", "0.00", "-70.00", "inf")
        graph = mix.build_filter_graph([2.0, 3.0], None, silent)
        self.assertNotIn("loudnorm", graph)
        self.assertIn(",anull,", graph)


class TestCaption(unittest.TestCase):

    def test_segments(self) -> None:
        """credit.caption_segments merges consecutive scenes of one colour into one time range and skips
        uncaptioned scenes. Guards one drawtext per colour run."""
        D, L = "dark", "light"
        self.assertEqual(credit.caption_segments([5, 10, 8, 7], [None, D, D, None]), [(5, 23, D)])
        self.assertEqual(credit.caption_segments([5, 10, 8], [D, None, L]), [(0, 5, D), (15, 23, L)])

    def test_one_drawtext_per_colour(self) -> None:
        """credit.caption_filter draws one drawtext per colour with all its ranges in one enable, returns None
        without segments, and credit.drawtext_filter refuses a path with a quote. Guards the filter syntax and
        FFmpeg filter-argument quoting."""
        f = credit.caption_filter(Path("/tmp/c.txt"), [(0, 5, "black@0.5"), (5, 15, "white@0.6"), (15, 23, "black@0.5")])
        first, second = f.split(",drawtext")
        self.assertIn("fontcolor=black@0.5", first)
        self.assertIn("enable='between(t,0,5)+between(t,15,23)'", first)
        self.assertIn("between(t,5,15)", second)
        self.assertIsNone(credit.caption_filter(Path("/tmp/c.txt"), []))
        with self.assertRaises(ValueError):
            credit.drawtext_filter(Path("/tmp/it's/c.txt"), "black@0.5")

    def test_colour_and_texts(self) -> None:
        """credit.caption_color picks dark text on a bright corner and light text on a dark one; cli.authors
        normalises names; caption_text, metadata_args and scenes.card_js give the caption, copyright tag and
        byline. Guards the creator credit texts."""
        self.assertEqual(credit.caption_color(240), "black@0.5")
        self.assertEqual(credit.caption_color(30), "white@0.6")
        names = cli.authors(["Alice  Smith", "Bob Jones"])
        self.assertEqual(credit.caption_text(names), "Created by Alice Smith, Bob Jones")
        self.assertEqual(credit.metadata_args("Jane", 2026)[-1], "copyright=© 2026 Jane")
        self.assertIsNone(cli.authors([" "]))
        self.assertIn('"byline": "by Jane"', scenes.card_js({"template": "title", "author": "Jane", "beats": ["T"]}))


class TestLogoOnlyCaption(unittest.TestCase):
    """`credit.text: null` and `credit.byline: null`: the logo alone, on every scene."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        (Path(self.dir.name) / settings.PROJECT_FILE).write_text("credit: {text: null, byline: null}\n")
        settings.use_project(Path(self.dir.name))

    def tearDown(self) -> None:
        settings.use_project(None)
        self.dir.cleanup()

    def test_no_text_logo_on_every_scene(self) -> None:
        """With credit.text and credit.byline null, credit draws no text, captions every scene and
        caption_filter overlays only the logo per colour (on-dark PNG for light text) through a null filter;
        without a brand nothing is drawn. Guards the logo-only caption mode."""
        self.assertIsNone(credit.caption_text("Jane"))
        self.assertIsNone(credit.write_caption(Path(self.dir.name), "Jane"))
        self.assertEqual(credit.captioned([True, False, True]), [True, True, True])
        self.assertEqual(credit.metadata_args("Jane", 2026)[-1], "copyright=© 2026 Jane")
        logo = credit.Logo(Path("/tmp/b/logo.png"), 1854, 1013, 21, 25, 33, Path("/tmp/b/logo_on_dark.png"))
        segs = [(0, 5, "white@0.6"), (5, 9, "black@0.5")]
        f = credit.caption_filter(None, segs, logo)
        self.assertNotIn("drawtext", f)
        self.assertTrue(f.startswith("null[cap0];movie='/tmp/b/logo_on_dark.png'"))
        self.assertIn("[cap1];movie='/tmp/b/logo.png'", f)
        self.assertIn("overlay=x=1854:y=1013:enable='between(t,5,9)'", f)
        self.assertIn("[vcat]null[cap0];", mix.build_filter_graph([5.0, 4.0], None, MEASURED, caption=f))
        self.assertIsNone(credit.caption_filter(None, segs))   # no text, no brand: nothing drawn

    def test_brightness_measured_around_the_logo(self) -> None:
        """credit.measured_region is the logo box plus margin, clipped to the frame, in logo-only mode and the
        caption corner otherwise. Guards the caption colour being chosen from the area it is drawn on."""
        logo = credit.Logo(Path("/tmp/b/logo.png"), 1854, 1013, 21, 25, 33)
        x, y, w, h = credit.measured_region(logo, (1920, 1080))
        self.assertAlmostEqual(x * 1920, 1854 - 25)
        self.assertAlmostEqual(y * 1080, 1013 - 25)
        self.assertAlmostEqual((x + w) * 1920, 1854 + 21 + 25)
        self.assertAlmostEqual((y + h) * 1080, 1013 + 25 + 25)
        edge = credit.Logo(Path("/tmp/b/logo.png"), 1900, 1060, 20, 20, 30)
        x, y, w, h = credit.measured_region(edge, (1920, 1080))
        self.assertAlmostEqual(x + w, 1.0)                       # clipped to the frame
        self.assertAlmostEqual(y + h, 1.0)
        self.assertEqual(credit.measured_region(None, (1920, 1080)), [0.6, 0.86, 0.4, 0.14])
        settings.use_project(None)                               # with text: the caption corner
        self.assertEqual(credit.measured_region(logo, (1920, 1080)), [0.6, 0.86, 0.4, 0.14])

    def test_cards_have_no_byline_or_credit(self) -> None:
        """scenes.card_js in logo-only mode writes null byline and credit for title and end cards but keeps the
        author. Guards the cards following credit.byline and credit.text."""
        for t in ("title", "end"):
            js = scenes.card_js({"template": t, "author": "Jane", "beats": ["T"]})
            self.assertIn('"byline": null', js)
            self.assertIn('"credit": null', js)
            self.assertIn('"author": "Jane"', js)

    def test_with_text_title_and_end_skipped(self) -> None:
        """credit.captioned with caption text captions exactly the scenes whose storyboard.show_author is True:
        not title and end, not a scene with `Show author: false`, the others yes. Guards no double credit on
        title and end cards and on a slide that already shows the author."""
        settings.use_project(None)
        self.assertEqual(credit.captioned([False, True]), [False, True])
        scenes = [{"id": "t", "template": "title"}, {"id": "a"}, {"id": "b", "show_author": False},
                  {"id": "e", "template": "end", "show_author": True}]
        self.assertEqual(credit.captioned([storyboard.show_author(s) for s in scenes]), [False, True, False, True])


class TestBrandLogo(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)

    def test_pixels(self) -> None:
        """credit.pixels evaluates h-relative expressions and refuses anything but arithmetic on h. Guards
        settings expressions not being evaluated as Python."""
        self.assertEqual(credit.pixels("h/40", 1080), 27)
        self.assertEqual(credit.pixels("h*0.05+2", 1000), 52)
        with self.assertRaises(ValueError):
            credit.pixels("__import__('os')", 1080)

    def test_logo_box_right_of_text_centred_on_cap_band(self) -> None:
        # 1080p: font 27 px, margin 45 px, cap height 0.717 x 27; a 1:2 logo.
        """credit.logo_box puts the logo on the right margin, its height from the cap height and the brand's
        caption ratio, centred on the cap band, and shifts the text one gap left. Guards the caption logo
        placement rule."""
        x, y, w, h, shift = credit.logo_box((1920, 1080), (100, 200), {"height": 1.3, "gap": 0.45})
        cap = 0.717 * 27
        self.assertEqual(h, round(1.3 * cap))
        self.assertEqual(w, round(h / 2))
        self.assertEqual(x + w, 1920 - 45)                       # right edge on the margin
        baseline = 1080 - 45
        self.assertAlmostEqual(y + h / 2, baseline - cap / 2, delta=0.5)  # centred on the cap band
        self.assertEqual(shift, round(w + 0.45 * 27))            # text ends one gap left of the logo

    def test_logo_box_scales_with_frame(self) -> None:
        """credit.logo_box scales the logo with the frame height. Guards the logo size at other resolutions."""
        small = credit.logo_box((960, 540), (100, 200), {"height": 1.3, "gap": 0.45})
        big = credit.logo_box((1920, 1080), (100, 200), {"height": 1.3, "gap": 0.45})
        self.assertAlmostEqual(big[3] / small[3], 2, delta=0.2)

    def test_filters_with_logo(self) -> None:
        """credit.caption_filter with a logo shifts the text left by the logo width and gap, overlays the scaled
        logo over the same ranges, and mix.build_filter_graph ends it in [v]; without a logo the text is
        unchanged. Guards the caption filter with a brand."""
        logo = credit.Logo(Path("/tmp/b/logo.png"), 1854, 1013, 21, 25, 33)
        segs = [(0, 5, "black@0.5"), (9, 12, "white@0.6")]
        f = credit.caption_filter(Path("/tmp/c.txt"), segs, logo)
        self.assertIn("x=w-tw-h/24-33:y=h-h/24:y_align=baseline", f)
        self.assertIn("[cap0];movie='/tmp/b/logo.png',scale=21:25:flags=lanczos,format=rgba[logo0]", f)
        self.assertTrue(f.endswith("[cap0][logo0]overlay=x=1854:y=1013:enable='between(t,0,5)+between(t,9,12)'"))
        graph = mix.build_filter_graph([5.0, 4.0, 3.0], None, MEASURED, caption=f)
        self.assertIn("[vcat]drawtext=", graph)
        self.assertIn("enable='between(t,0,5)+between(t,9,12)'[v]", graph)
        # No brand: the caption is unchanged.
        self.assertNotIn("movie=", credit.caption_filter(Path("/tmp/c.txt"), segs))
        self.assertIn("y=h-th-h/24", credit.caption_filter(Path("/tmp/c.txt"), segs))

    def test_logo_on_dark_per_segment(self) -> None:
        """credit.Logo.png and caption_filter use the raster_on_dark PNG for light-text segments and raster for
        the others, one overlay per PNG; without raster_on_dark every segment uses raster. Guards the per-scene
        logo choice."""
        logo = credit.Logo(Path("/tmp/b/logo.png"), 1854, 1013, 21, 25, 33, Path("/tmp/b/logo_on_dark.png"))
        self.assertEqual(logo.png("white@0.6"), Path("/tmp/b/logo_on_dark.png"))  # light text: dark corner
        self.assertEqual(logo.png("black@0.5"), Path("/tmp/b/logo.png"))
        segs = [(0, 5, "black@0.5"), (5, 9, "white@0.6"), (9, 12, "black@0.5")]
        f = credit.caption_filter(Path("/tmp/c.txt"), segs, logo)
        self.assertIn("[cap0];movie='/tmp/b/logo.png',scale=21:25:flags=lanczos,format=rgba[logo0];"
                      "[cap0][logo0]overlay=x=1854:y=1013:enable='between(t,0,5)+between(t,9,12)'"
                      "[cap1];movie='/tmp/b/logo_on_dark.png',scale=21:25:flags=lanczos,format=rgba[logo1];"
                      "[cap1][logo1]overlay=x=1854:y=1013:enable='between(t,5,9)'", f)
        self.assertTrue(f.endswith("enable='between(t,5,9)'"))
        # Only dark corners: the on-dark PNG alone, as the first overlay.
        f = credit.caption_filter(Path("/tmp/c.txt"), [(0, 5, "white@0.6")], logo)
        self.assertNotIn("movie='/tmp/b/logo.png'", f)
        self.assertIn("[cap0];movie='/tmp/b/logo_on_dark.png'", f)
        # Without an on-dark PNG every segment gets `path`.
        plain = credit.Logo(Path("/tmp/b/logo.png"), 1854, 1013, 21, 25, 33)
        f = credit.caption_filter(Path("/tmp/c.txt"), segs, plain)
        self.assertNotIn("[cap1]", f)
        self.assertTrue(f.endswith("enable='between(t,0,5)+between(t,5,9)+between(t,9,12)'"))

    def test_raster_on_dark_validation(self) -> None:
        """brand.load accepts a raster_on_dark PNG of the raster's aspect at another resolution and refuses
        another aspect, a missing file and a non-PNG; credit.caption_logo copies both PNGs. Guards
        brand.load_dir's raster_on_dark check."""
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "mine"
            folder.mkdir()
            solid_png(folder / "light.png", 40, 50, (255, 0, 0))
            solid_png(folder / "dark.png", 80, 100, (0, 200, 0))   # same aspect, other resolution
            solid_png(folder / "wide.png", 60, 50, (0, 200, 0))
            head = "raster: light.png\ncaption: {height: 1, gap: 0.5}\n"
            (folder / "brand.yaml").write_text(head + "raster_on_dark: dark.png\n")
            b = brand.load("mine", folder)
            logo = credit.caption_logo(b, (1920, 1080), Path(d))
            self.assertEqual(logo.on_dark, Path(d) / "logo_on_dark.png")
            self.assertEqual(logo.on_dark.read_bytes(), (folder / "dark.png").read_bytes())
            self.assertEqual(logo.path.read_bytes(), (folder / "light.png").read_bytes())
            (folder / "brand.yaml").write_text(head)
            self.assertIsNone(credit.caption_logo(brand.load("mine", folder), (1920, 1080), Path(d)).on_dark)
            (folder / "brand.yaml").write_text(head + "raster_on_dark: wide.png\n")
            with self.assertRaisesRegex(ValueError, "`raster_on_dark:` wide.png .60x50. must have the aspect ratio"):
                brand.load("mine", folder)
            (folder / "brand.yaml").write_text(head + "raster_on_dark: missing.png\n")
            with self.assertRaisesRegex(ValueError, "`raster_on_dark:` .* must name a PNG"):
                brand.load("mine", folder)
            (folder / "brand.yaml").write_text(head + "raster_on_dark: brand.yaml\n")
            with self.assertRaisesRegex(ValueError, "`raster_on_dark:` .* must name a PNG"):
                brand.load("mine", folder)

    def test_no_brand_name(self) -> None:
        """brand.load returns None without a brand name and brand.problems reports a folder given without
        `brand:`. Guards films without a brand and the validate warning."""
        self.assertIsNone(brand.load(None))
        self.assertIsNone(brand.load(None, BRAND_SRC))
        self.assertEqual(brand.problems(None), [])
        # A folder without `brand:` is reported: `assemble` refuses it.
        self.assertIn("no `brand:` is set", brand.problems(None, BRAND_SRC)[0])

    def test_name_without_folder_names_the_brand_skill(self) -> None:
        """brand.load and brand.problems with a brand name but no folder name the brand skill and --brand.
        Guards the message that tells the agent where the folder comes from."""
        with self.assertRaisesRegex(ValueError, r"brand skill \(`brand:brand`\).*--brand"):
            brand.load("acme")
        found = brand.problems("acme")
        self.assertEqual(len(found), 1)
        self.assertIn("`brand:brand`", found[0])
        self.assertIn("`assemble` refuses", found[0])

    def test_folder_of_another_brand(self) -> None:
        """brand.load and brand.problems refuse a folder whose name is not the `brand:` value. Guards the
        folder-name rule."""
        with self.assertRaisesRegex(ValueError, "folder of brand 'acme'.*name brand 'globex'"):
            brand.load("globex", BRAND_SRC)
        self.assertIn("name brand 'globex'", brand.problems("globex", BRAND_SRC)[0])

    def test_folder_without_brand_yaml(self) -> None:
        """brand.load and brand.resolve refuse a folder without brand.yaml, also a missing path, before
        comparing names. Guards the order of the checks and their message."""
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "acme"
            folder.mkdir()
            with self.assertRaisesRegex(ValueError, "no brand.yaml in it"):
                brand.load("acme", folder)
            with self.assertRaisesRegex(ValueError, "no brand.yaml in it"):
                brand.resolve(folder)
            with self.assertRaisesRegex(ValueError, "no brand.yaml in it"):
                brand.resolve(Path(d) / "missing")
            # A path that does not exist reports the missing brand.yaml, not its name.
            with self.assertRaisesRegex(ValueError, "no brand.yaml in it"):
                brand.load("acme", Path(d) / "globex")

    def test_test_brand_loads_in_place(self) -> None:
        """brand.load and brand.resolve read the acme test brand folder in place with no problems. Guards
        that a brand folder of the brand skill's format meets short-video's brand.yaml keys."""
        b = brand.load("acme", BRAND_SRC)
        self.assertEqual(b["dir"], BRAND_SRC)
        self.assertGreater(brand.png_size(b["dir"] / b["raster"])[1], 0)
        self.assertEqual(brand.problems("acme", BRAND_SRC), [])
        self.assertEqual(brand.resolve(str(BRAND_SRC))["dir"], BRAND_SRC)

    def test_folder_problems(self) -> None:
        """brand.problems reports a logo that is not SVG or PNG, a missing logo key and missing caption ratios,
        and brand.load refuses a missing raster. Guards validate's brand checks."""
        png = (BRAND_SRC / "logo.png").read_bytes()
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "mine"
            folder.mkdir()
            (folder / "brand.yaml").write_text("logo: logo.jpg\nraster: logo.png\ncaption: {height: 1, gap: 0.5}\n")
            (folder / "logo.jpg").write_bytes(b"x")
            (folder / "logo.png").write_bytes(png)
            self.assertIn("not an SVG or PNG", brand.problems("mine", folder)[0])
            (folder / "brand.yaml").write_text("raster: logo.png\ncaption: {height: 1, gap: 0.5}\n")
            self.assertIn("`logo:`", brand.problems("mine", folder)[0])
            (folder / "brand.yaml").write_text("logo: logo.svg\nraster: logo.png\n")
            self.assertIn("needs numeric `height` and `gap`", brand.problems("mine", folder)[0])
            (folder / "brand.yaml").write_text("logo: logo.png\nraster: logo.png\ncaption: {height: 1, gap: 0.5}\n")
            (folder / "logo.png").unlink()
            with self.assertRaisesRegex(ValueError, "`raster:`"):
                brand.load("mine", folder)

    def test_credit_brand_option(self) -> None:
        """cli credit takes --brand DIR, no -p, and stops on a folder without brand.yaml before any encode.
        Guards credit taking a brand folder only."""
        args = cli._build_parser().parse_args(["credit", "in.mp4", "--author", "Jane Doe", "--brand", "/b/acme"])
        self.assertEqual(args.brand, "/b/acme")
        args = cli._build_parser().parse_args(["credit", "in.mp4", "--author", "Jane Doe"])
        self.assertIsNone(args.brand)
        with self.assertRaises(SystemExit):  # -p is gone: credit takes a brand folder only
            cli._build_parser().parse_args(["credit", "in.mp4", "--author", "J", "-p", "/tmp/film"])
        # A folder without brand.yaml stops before any encode.
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.mp4"
            src.write_bytes(b"")
            args = cli._build_parser().parse_args(["credit", str(src), "--author", "Jane Doe", "--brand", d])
            with self.assertRaises(SystemExit):
                args.func(args)

    def test_validate_settings_brand_warnings(self) -> None:
        """storyboard.validate_settings warns naming `brand:brand` and --brand when `brand:` is set without a
        folder, and not with one. Guards validate reporting what assemble would refuse."""
        with tempfile.TemporaryDirectory() as d:
            project = Path(d)
            (project / "settings.yaml").write_text("author: [Jane Doe]\nbrand: acme\n")
            settings.use_project(project)
            try:
                without = storyboard.validate_settings(project)
                with_folder = storyboard.validate_settings(project, BRAND_SRC)
            finally:
                settings.use_project(None)
        self.assertEqual(without.errors, [])
        self.assertTrue(any("`brand:brand`" in w and "--brand" in w for w in without.warnings), without.warnings)
        self.assertEqual(with_folder.errors, [])
        self.assertFalse(any("brand" in w for w in with_folder.warnings), with_folder.warnings)


class TestAssembleBrand(unittest.TestCase):
    """`assemble` checks the brand before it looks at scenes."""

    def assemble(self, settings_text: str, brand_dir: Path | None) -> str:
        with tempfile.TemporaryDirectory() as d:
            project = Path(d)
            (project / "settings.yaml").write_text(settings_text)
            settings.use_project(project)
            try:
                with self.assertRaises(mix.AssembleError) as cm:
                    mix.assemble(project, {"scenes": []}, brand_dir=brand_dir)
            finally:
                settings.use_project(None)
        return str(cm.exception)

    def test_brand_set_without_folder_names_the_brand_skill(self) -> None:
        """mix.assemble with `brand:` set and no folder raises AssembleError naming the brand skill and --brand.
        Guards assemble turning brand.load's ValueError into one error."""
        msg = self.assemble("author: [Jane Doe]\nbrand: acme\n", None)
        self.assertIn("brand skill (`brand:brand`)", msg)
        self.assertIn("--brand", msg)

    def test_folder_without_brand_setting(self) -> None:
        """mix.assemble with --brand and no `brand:` set refuses. Guards a brand folder never being used without
        the setting."""
        msg = self.assemble("author: [Jane Doe]\n", BRAND_SRC)
        self.assertIn("no `brand:` is set", msg)


if __name__ == "__main__":
    unittest.main()
