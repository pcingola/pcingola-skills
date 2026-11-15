"""Unit tests for brand_tool: lookup order, BRAND_PATH parsing, the settings file, copy,
and the bundled brands against the brand folder specification in SKILL.md.

brand_tool reads BRAND_PATH from config.yaml, so every lookup runs in a child process
with HOME in a temp directory and SKILLS_CONFIG naming a config.yaml that sets
BRAND_PATH as the test gives it."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import yaml

from brand_tool import config
from tests.prereq import requires
from tests.settings_env import write_config
from tests.subproc import child_env, run_python

# A brand outside the plugin, for BRAND_PATH tests: tests/brands/acme.
TEST_BRANDS = Path(__file__).resolve().parents[2] / "brands"

CALL = """
import json
from pathlib import Path
from brand_tool import cli, config
from brand_tool.config import BrandError
try:
    print(json.dumps({{"ok": {expr}}}, default=str))
except BrandError as e:
    print(json.dumps({{"error": str(e)}}))
"""


def make_brand(root: Path, name: str, text: str = "logo: logo.svg\n") -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "brand.yaml").write_text(text, encoding="utf-8")
    return folder


def pairs(brands: list) -> list[tuple[str, str]]:
    """config.list_brands output with str paths, as the child returns it."""
    return [(name, str(path)) for name, path in brands]


class TmpCase(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.bundled = self.tmp / "bundled"
        self.bundled.mkdir()
        self.a = self.tmp / "a"
        self.b = self.tmp / "b"
        self.a.mkdir()
        self.b.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def env(self, brand_path: str | None, **extra: str) -> dict[str, str]:
        """A child environment whose config.yaml sets BRAND_PATH to `brand_path` (no setting when None)."""
        cfg = write_config(self.tmp / "config.yaml", {} if brand_path is None else {"BRAND_PATH": brand_path})
        return child_env({"HOME": str(self.tmp / "home"), "SKILLS_CONFIG": str(cfg), **extra})

    def call(self, brand_path: str | None, expr: str) -> dict:
        """Evaluate `expr` (cli, config and Path imported) in a child process with BRAND_PATH brand_path;
        return {"ok": value with str paths} or {"error": BrandError message}."""
        done = run_python(CALL.format(expr=expr), self.env(brand_path))
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def ok(self, brand_path: str | None, expr: str):
        got = self.call(brand_path, expr)
        self.assertIn("ok", got, got)
        return got["ok"]

    def error(self, brand_path: str | None, expr: str) -> str:
        got = self.call(brand_path, expr)
        self.assertIn("error", got, got)
        return got["error"]

    def copy(self, brand_path: str, dest: Path, force: bool = False) -> str:
        return f"cli.copy_brand('acme', Path({str(dest)!r}), force={force}, bundled=Path({str(self.bundled)!r}))"

    def search_dirs(self, bundled: Path) -> str:
        return f"config.search_dirs(Path({str(bundled)!r}))"

    def find(self, name: str = "acme") -> str:
        return f"config.find({name!r}, Path({str(self.bundled)!r}))"

    def list_brands(self) -> str:
        return f"config.list_brands(Path({str(self.bundled)!r}))"


class TestSearchOrder(TmpCase):

    def test_bundled_first_then_brand_path_in_order(self) -> None:
        """config.search_dirs returns the bundled directory first, then BRAND_PATH
        entries in their order. Guards the search order SKILL.md defines."""
        got = self.ok(f"{self.b}:{self.a}", self.search_dirs(self.bundled))
        self.assertEqual(got, [str(self.bundled), str(self.b), str(self.a)])

    def test_bundled_wins_over_brand_path(self) -> None:
        """config.find returns the bundled brand when BRAND_PATH holds one of the same
        name. Guards that bundled brands come first."""
        bundled = make_brand(self.bundled, "acme")
        make_brand(self.a, "acme")
        self.assertEqual(self.ok(str(self.a), self.find()), str(bundled))

    def test_first_brand_path_entry_wins(self) -> None:
        """config.find returns the brand from the earlier BRAND_PATH entry when two
        entries hold the name. Guards the first-match rule."""
        make_brand(self.a, "acme")
        in_b = make_brand(self.b, "acme")
        self.assertEqual(self.ok(f"{self.b}:{self.a}", self.find()), str(in_b))

    def test_folder_without_brand_yaml_is_skipped(self) -> None:
        """config.find skips a folder of the right name that has no brand.yaml and
        continues with later entries. Guards that only folders with brand.yaml are
        brands."""
        (self.a / "acme").mkdir()
        in_b = make_brand(self.b, "acme")
        self.assertEqual(self.ok(f"{self.a}:{self.b}", self.find()), str(in_b))

    def test_list_first_match_per_name(self) -> None:
        """config.list_brands lists each name once, at its first match, in search order.
        Guards `brand list` showing the folder `show` would resolve."""
        make_brand(self.bundled, "zeta")
        make_brand(self.a, "acme")
        make_brand(self.b, "acme")
        make_brand(self.b, "beta")
        got = self.ok(f"{self.a}:{self.b}", self.list_brands())
        self.assertEqual(got, [list(p) for p in pairs(
            [("zeta", self.bundled / "zeta"), ("acme", self.a / "acme"), ("beta", self.b / "beta")])])

    def test_test_brand_through_brand_path(self) -> None:
        """config.list_brands and config.find with BRAND_PATH set to tests/brands
        find the bundled neutral brand first, then the acme test brand. Guards lookup
        of a real brand folder outside the plugin."""
        got = self.ok(str(TEST_BRANDS), "[config.list_brands(), config.find('acme'), config.find('neutral')]")
        self.assertEqual(got, [
            [list(p) for p in pairs([("neutral", config.BUNDLED_DIR / "neutral"), ("acme", TEST_BRANDS / "acme")])],
            str(TEST_BRANDS / "acme"),
            str(config.BUNDLED_DIR / "neutral"),
        ])


class TestBrandPathEntries(TmpCase):

    def test_unset(self) -> None:
        """config.search_dirs without BRAND_PATH is the bundled directory alone. Guards
        that an unset setting adds no entry such as the current directory."""
        self.assertEqual(self.ok(None, self.search_dirs(self.bundled)), [str(self.bundled)])

    def test_empty_entries_skipped(self) -> None:
        """config.search_dirs skips empty and blank BRAND_PATH entries. Guards against
        an empty entry becoming `.`."""
        self.assertEqual(self.ok(f"::{self.a}: :", self.search_dirs(self.bundled)), [str(self.bundled), str(self.a)])

    def test_missing_entries_skipped(self) -> None:
        """config.search_dirs skips a BRAND_PATH entry that is no directory. Guards the
        documented skip of missing entries."""
        missing = self.tmp / "missing"
        got = self.ok(f"{missing}:{self.a}", self.search_dirs(self.bundled))
        self.assertEqual(got, [str(self.bundled), str(self.a)])

    def test_missing_bundled_skipped(self) -> None:
        """config.search_dirs leaves out a bundled directory that does not exist. Guards
        a plugin copy without brands/."""
        self.assertEqual(self.ok(str(self.a), self.search_dirs(self.tmp / "nope")), [str(self.a)])

    def test_duplicate_entries_once(self) -> None:
        """config.search_dirs lists a repeated BRAND_PATH entry once. Guards the
        duplicate removal on resolved paths."""
        got = self.ok(f"{self.a}:{self.a}", self.search_dirs(self.bundled))
        self.assertEqual(got, [str(self.bundled), str(self.a)])

    def test_not_found_names_searched_dirs(self) -> None:
        """config.find raises BrandError naming every searched directory when no brand
        matches. Guards the error that shows the user where to put a brand."""
        err = self.error(str(self.a), self.find())
        self.assertIn(str(self.bundled), err)
        self.assertIn(str(self.a), err)

    def test_invalid_names(self) -> None:
        """config.find refuses empty, `.`, `..` and path-like names. Guards check_name,
        which keeps a name from escaping the search directories."""
        for name in ("", ".", "..", "a/b"):
            with self.subTest(name=name):
                self.error(None, self.find(name))


class TestCopy(TmpCase):

    def test_copy_to_dest_name(self) -> None:
        """cli.copy_brand copies the whole brand folder, subfolders included, to
        `<dest>/<name>/`. Guards the target layout of `brand copy`."""
        src = make_brand(self.a, "acme")
        (src / "pptx").mkdir()
        (src / "pptx" / "t.pptx").write_bytes(b"x")
        dest = self.tmp / "project" / "brand"
        target = Path(self.ok(str(self.a), self.copy(str(self.a), dest)))
        self.assertEqual(target, dest / "acme")
        self.assertEqual((target / "brand.yaml").read_text(), "logo: logo.svg\n")
        self.assertEqual((target / "pptx" / "t.pptx").read_bytes(), b"x")

    def test_refuses_existing_target(self) -> None:
        """cli.copy_brand without force refuses an existing target and leaves it
        unchanged. Guards against overwriting a customised brand."""
        make_brand(self.a, "acme", "new\n")
        dest = self.tmp / "dest"
        make_brand(dest, "acme", "old\n")
        self.error(str(self.a), self.copy(str(self.a), dest))
        self.assertEqual((dest / "acme" / "brand.yaml").read_text(), "old\n")

    def test_force_replaces_target(self) -> None:
        """cli.copy_brand with force replaces the target, files absent from the source
        removed. Guards that --force yields an exact copy."""
        make_brand(self.a, "acme", "new\n")
        dest = self.tmp / "dest"
        old = make_brand(dest, "acme", "old\n")
        (old / "stale.txt").write_text("s")
        self.ok(str(self.a), self.copy(str(self.a), dest, force=True))
        self.assertEqual((dest / "acme" / "brand.yaml").read_text(), "new\n")
        self.assertFalse((dest / "acme" / "stale.txt").exists())

    def test_refuses_copy_onto_itself(self) -> None:
        """cli.copy_brand refuses a target equal to the source, even with force. Guards
        against deleting the source while replacing the target."""
        make_brand(self.a, "acme")
        self.error(str(self.a), self.copy(str(self.a), self.a, force=True))
        self.assertTrue((self.a / "acme" / "brand.yaml").is_file())

    def test_refuses_target_inside_source(self) -> None:
        """cli.copy_brand refuses a target inside the source folder. Guards the overlap
        check against a copy into itself."""
        src = make_brand(self.a, "acme")
        self.error(str(self.a), self.copy(str(self.a), src / "sub"))
        self.assertFalse((src / "sub").exists())

    def test_refuses_target_holding_source(self) -> None:
        # BRAND_PATH entry x/acme/inner: the target x/acme contains the source x/acme/inner/acme.
        """cli.copy_brand refuses a target that contains the source, here a BRAND_PATH
        entry under the target. Guards the reverse overlap check, which with force
        would delete the source."""
        inner = self.a / "acme" / "inner"
        src = make_brand(inner, "acme")
        self.error(str(inner), self.copy(str(inner), self.a, force=True))
        self.assertTrue((src / "brand.yaml").is_file())

    def test_force_replaces_symlink_to_source(self) -> None:
        """cli.copy_brand with force replaces a target that is a symlink to the source
        with a real copy and keeps the source. Guards that a symlinked target is
        replaced, never followed, so the source is not deleted."""
        src = make_brand(self.a, "acme")
        dest = self.tmp / "dest"
        dest.mkdir()
        (dest / "acme").symlink_to(src)
        self.ok(str(self.a), self.copy(str(self.a), dest, force=True))
        self.assertFalse((dest / "acme").is_symlink())
        self.assertTrue((dest / "acme" / "brand.yaml").is_file())
        self.assertTrue((src / "brand.yaml").is_file())

    def test_refuses_symlinked_target_inside_source(self) -> None:
        """cli.copy_brand refuses a target inside the source even when the target is a
        symlink elsewhere, and leaves the symlink. Guards a past bug: a symlinked
        target skipped the overlap check (commit b912d79)."""
        src = make_brand(self.a, "acme")
        (src / "sub").mkdir()
        (src / "sub" / "acme").symlink_to(self.b)
        err = self.error(str(self.a), self.copy(str(self.a), src / "sub", force=True))
        self.assertIn("overlap", err)
        self.assertTrue((src / "sub" / "acme").is_symlink())

    def test_force_replaces_file_target(self) -> None:
        """cli.copy_brand with force replaces a regular file at the target. Guards the
        unlink branch for a non-directory target."""
        make_brand(self.a, "acme")
        dest = self.tmp / "dest"
        dest.mkdir()
        (dest / "acme").write_text("x")
        self.ok(str(self.a), self.copy(str(self.a), dest, force=True))
        self.assertTrue((dest / "acme" / "brand.yaml").is_file())

    def test_dest_is_a_file(self) -> None:
        """cli.copy_brand raises BrandError when dest is a file. Guards that OS errors
        are reported as BrandError, not a traceback."""
        make_brand(self.a, "acme")
        dest = self.tmp / "file"
        dest.write_text("x")
        self.error(str(self.a), self.copy(str(self.a), dest))

    @requires(os.geteuid() != 0, "root reads any directory")
    def test_list_skips_unreadable_dir(self) -> None:
        """config.list_brands and config.find skip a BRAND_PATH directory they cannot
        read. Guards the OSError handling added when lookup was hardened."""
        make_brand(self.b, "acme")
        self.a.chmod(0)
        try:
            got = self.ok(f"{self.a}:{self.b}", f"[{self.list_brands()}, {self.find()}]")
        finally:
            self.a.chmod(0o755)
        self.assertEqual(got, [[["acme", str(self.b / "acme")]], str(self.b / "acme")])


class TestCli(TmpCase):

    def run_cli(self, brand_path: str | None, *argv: str, **extra: str) -> subprocess.CompletedProcess:
        """`python -m brand_tool <argv>` in a child process with BRAND_PATH brand_path."""
        return subprocess.run([sys.executable, "-m", "brand_tool", *argv], capture_output=True, text=True,
                              env=self.env(brand_path, **extra))

    def test_show_prints_folder_then_yaml(self) -> None:
        """`brand show` prints the resolved folder on the first line, then brand.yaml
        verbatim. Guards the output format callers parse (SKILL.md)."""
        folder = make_brand(self.a, "acme", "logo: x.svg\ncolors:\n  a: '#000000'\n")
        done = self.run_cli(str(self.a), "show", "acme")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, f"{folder}\nlogo: x.svg\ncolors:\n  a: '#000000'\n")

    def test_show_missing_exits_1(self) -> None:
        """`brand show` of an unknown brand exits 1 with the searched directories on
        stderr and nothing on stdout. Guards the CLI error path."""
        done = self.run_cli(str(self.a), "show", "acme")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, "")
        self.assertIn(str(self.a), done.stderr)

    def test_copy_refusal_exits_1(self) -> None:
        """`brand copy` onto an existing target exits 1 and names --force. Guards the
        CLI message for the refusal."""
        make_brand(self.a, "acme")
        dest = self.tmp / "dest"
        make_brand(dest, "acme")
        done = self.run_cli(str(self.a), "copy", "acme", str(dest))
        self.assertEqual(done.returncode, 1)
        self.assertIn("--force", done.stderr)

    def test_list(self) -> None:
        """`brand list` prints each name and its folder. Guards the list output format."""
        make_brand(self.a, "acme")
        done = self.run_cli(str(self.a), "list")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(["acme", str(self.a / "acme")], [line.split() for line in done.stdout.splitlines()])

    def test_list_ignores_brand_path_in_environment(self) -> None:
        """`brand list` ignores a process variable BRAND_PATH. Guards config.yaml as the only
        source of the setting."""
        make_brand(self.a, "acme")
        done = self.run_cli(None, "list", BRAND_PATH=str(self.a))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn(str(self.a), done.stdout)


# The brand.yaml keys the checks below cover; test_spec_table_matches compares
# them with the key table in SKILL.md ("brand.yaml").
PATH_KEYS = ("logo", "raster", "raster_on_dark")
KEYS = {"logo", "logos", "raster", "raster_on_dark", "caption", "colors", "fonts", "pptx", "styles"}
SKILL_MD = config.BUNDLED_DIR.parent / "SKILL.md"
# The style skill's style files, next to the brand skill in the brand plugin.
STYLE_REFERENCES = config.BUNDLED_DIR.parent.parent / "style" / "references"
COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
# The colours of the image prompt palette (SKILL.md, "Keys per medium").
PALETTE_KEYS = ("accent1", "accent2", "accent3", "dk1", "lt1")


class TestBundledBrandsConform(unittest.TestCase):
    """Each bundled brand matches the brand folder specification in SKILL.md."""

    def brands(self) -> list[Path]:
        """The bundled brands and the acme test brand, which must meet the same spec."""
        folders = sorted(p for p in config.BUNDLED_DIR.iterdir() if p.is_dir())
        self.assertTrue(folders)
        return folders + [TEST_BRANDS / "acme"]

    def spec(self, folder: Path) -> dict:
        data = yaml.safe_load((folder / config.BRAND_FILE).read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict, folder)
        return data

    def assert_file(self, folder: Path, value, what: str) -> Path:
        self.assertIsInstance(value, str, f"{folder.name}: {what}")
        path = folder / value
        self.assertTrue(path.is_file(), f"{folder.name}: {what} names {value}, which does not exist")
        return path

    def test_spec_table_matches(self) -> None:
        """The brand.yaml key table in SKILL.md lists exactly the keys these conformance
        tests check. Guards that the specification and its test stay in step."""
        text = SKILL_MD.read_text(encoding="utf-8")
        section = text.split("## brand.yaml", 1)[1].split("\n## ", 1)[0]
        rows = [line for line in section.splitlines() if line.startswith("| `")]
        documented = {re.match(r"\| `([a-z_]+)`", line).group(1) for line in rows}
        self.assertEqual(documented, KEYS)

    def test_keys_and_files(self) -> None:
        """Every bundled brand uses only specified keys, has guidelines.md, and its path
        keys name existing files with the specified suffixes. Guards the bundled
        brands against the SKILL.md specification."""
        for folder in self.brands():
            with self.subTest(brand=folder.name):
                data = self.spec(folder)
                self.assertLessEqual(set(data), KEYS)
                self.assertTrue((folder / "guidelines.md").is_file())
                for key in PATH_KEYS:
                    if key in data:
                        self.assert_file(folder, data[key], key)
                if "logo" in data:
                    self.assertIn(Path(data["logo"]).suffix.lower(), (".svg", ".png"))
                if "logos" in data:
                    self.assertIsInstance(data["logos"], dict)
                    self.assertTrue(data["logos"])
                    for name, value in data["logos"].items():
                        path = self.assert_file(folder, value, f"logos.{name}")
                        self.assertIn(path.suffix.lower(), (".svg", ".png"))
                for key in ("raster", "raster_on_dark"):
                    if key in data:
                        self.assertEqual(Path(data[key]).suffix.lower(), ".png")

    def test_caption(self) -> None:
        """Every bundled brand's caption has numeric height and gap. Guards the ratios
        short-video's credit overlay computes with."""
        for folder in self.brands():
            cap = self.spec(folder).get("caption")
            if cap is None:
                continue
            with self.subTest(brand=folder.name):
                self.assertIsInstance(cap, dict)
                for k in ("height", "gap"):
                    self.assertIsInstance(cap.get(k), (int, float))
                    self.assertNotIsInstance(cap.get(k), bool)

    def test_colors_and_fonts(self) -> None:
        """Every bundled brand's colours are #RRGGBB strings and its fonts are strings.
        Guards the value formats SKILL.md specifies."""
        for folder in self.brands():
            data = self.spec(folder)
            with self.subTest(brand=folder.name):
                colors, fonts = data.get("colors", {}), data.get("fonts", {})
                self.assertIsInstance(colors, dict)
                self.assertIsInstance(fonts, dict)
                for name, value in colors.items():
                    self.assertTrue(isinstance(value, str) and COLOR.fullmatch(value), f"colors.{name}: {value!r}")
                for role, family in fonts.items():
                    self.assertIsInstance(family, str, f"fonts.{role}")

    def test_palette_colors(self) -> None:
        """Every bundled brand has the colours callers put into an image prompt as the
        palette. Guards the keys SKILL.md says every bundled brand has."""
        for folder in self.brands():
            with self.subTest(brand=folder.name):
                self.assertLessEqual(set(PALETTE_KEYS), set(self.spec(folder).get("colors", {})))

    def test_pptx_templates(self) -> None:
        """Every bundled brand's pptx entries name an existing .pptx and .json and
        nothing else. Guards the template lookup by pptx key used by the slide
        skills."""
        for folder in self.brands():
            templates = self.spec(folder).get("pptx")
            if templates is None:
                continue
            with self.subTest(brand=folder.name):
                self.assertIsInstance(templates, dict)
                self.assertTrue(templates)
                for name, entry in templates.items():
                    self.assertIsInstance(entry, dict, name)
                    self.assertEqual(set(entry), {"pptx", "json"}, name)
                    self.assertEqual(self.assert_file(folder, entry["pptx"], f"pptx.{name}.pptx").suffix, ".pptx")
                    self.assertEqual(self.assert_file(folder, entry["json"], f"pptx.{name}.json").suffix, ".json")

    def test_styles(self) -> None:
        """Every bundled brand's styles is a list of unique names, each with a style
        file in the style skill's references/. Guards that a brand names only styles
        brand:style defines."""
        for folder in self.brands():
            styles = self.spec(folder).get("styles")
            if styles is None:
                continue
            with self.subTest(brand=folder.name):
                self.assertIsInstance(styles, list)
                self.assertTrue(styles)
                self.assertEqual(len(styles), len(set(styles)))
                for name in styles:
                    self.assertIsInstance(name, str)
                    self.assertTrue((STYLE_REFERENCES / f"{name}.md").is_file(), f"styles: {name} has no style file")


NEUTRAL_LAYOUTS = ["Title Slide", "Section Header", "Title and Content", "Two Content", "Blank"]
P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class TestNeutralPptx(unittest.TestCase):
    """The neutral PowerPoint template, read from the zip without python-pptx."""

    def setUp(self) -> None:
        self.folder = config.BUNDLED_DIR / "neutral"
        spec = yaml.safe_load((self.folder / config.BRAND_FILE).read_text(encoding="utf-8"))
        self.spec = spec
        self.pptx = self.folder / spec["pptx"]["presentation"]["pptx"]

    def part(self, name: str) -> ElementTree.Element:
        with zipfile.ZipFile(self.pptx) as z:
            return ElementTree.fromstring(z.read(name))

    def test_size_and_no_slides(self) -> None:
        """The template is 16:9 (12192000 x 6858000 EMU) and holds no slide. Guards the
        canvas guidelines.md states and the empty template."""
        pres = self.part("ppt/presentation.xml")
        size = pres.find(f"{P_NS}sldSz")
        self.assertEqual((size.get("cx"), size.get("cy")), ("12192000", "6858000"))
        self.assertEqual(list(pres.find(f"{P_NS}sldIdLst") or []), [])
        with zipfile.ZipFile(self.pptx) as z:
            self.assertFalse([n for n in z.namelist() if n.startswith("ppt/slides/")])

    def test_layouts(self) -> None:
        """The slide master lists exactly the five standard layouts, in order. Guards
        the layout names callers pick by name."""
        rels = self.part("ppt/slideMasters/_rels/slideMaster1.xml.rels")
        targets = {r.get("Id"): r.get("Target") for r in rels.iter(f"{REL_NS}Relationship")}
        master = self.part("ppt/slideMasters/slideMaster1.xml")
        names = []
        for entry in master.find(f"{P_NS}sldLayoutIdLst"):
            target = targets[entry.get(f"{R_NS}id")].replace("../", "ppt/")
            names.append(self.part(target).find(f"{P_NS}cSld").get("name"))
        self.assertEqual(names, NEUTRAL_LAYOUTS)

    def test_theme_matches_brand_yaml(self) -> None:
        """The theme's colour scheme holds every theme colour brand.yaml names and its
        font scheme the heading and body fonts. Guards the template against drift from
        brand.yaml."""
        theme = self.part("ppt/theme/theme1.xml")
        scheme = theme.find(f".//{A_NS}clrScheme")
        for slot, value in self.spec["colors"].items():
            el = scheme.find(f"{A_NS}{slot}")
            if el is None:
                continue  # not a theme slot (caption, chip colours)
            self.assertEqual(el.find(f"{A_NS}srgbClr").get("val"), value.lstrip("#").upper(), slot)
        fonts = theme.find(f".//{A_NS}fontScheme")
        self.assertEqual(fonts.find(f"{A_NS}majorFont/{A_NS}latin").get("typeface"), self.spec["fonts"]["heading"])
        self.assertEqual(fonts.find(f"{A_NS}minorFont/{A_NS}latin").get("typeface"), self.spec["fonts"]["body"])


if __name__ == "__main__":
    unittest.main()
