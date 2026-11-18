"""short_video_tool.particle_text and the `particle-text` command: targets and glyph textures of text blocks from
real font files (short-video SKILL.md, Commands; assets/techniques/particle_text/note.md). The fonts are OFL and
MIT fonts the repository already ships with the reveal.js skill."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from short_video_tool import config, particle_text, settings
from short_video_tool.particle_text import LETTER_STEP, SUPERSAMPLE, ParticleText
from tests.integration.short_video import cli

REPO = config.SCRIPTS_DIR.parents[4]
REVEAL = REPO / "plugins/docs/skills/revealjs-slideshow/assets/reveal.js"
TTF = REVEAL / "dist/theme/fonts/source-sans-pro/source-sans-pro-semibold.ttf"
WOFF2 = REVEAL / "plugin/math/katex/dist/fonts/KaTeX_Main-Bold.woff2"
TECHNIQUE = config.SCRIPTS_DIR.parent / "assets/techniques/particle_text"
# The command that made the technique's placeholder files (note.md, "Another word").
TECHNIQUE_ARGS = ["Title", "--font", str(TTF), "--name", "title", "--size", "300", "--tracking", "0.02",
                  "--count", "20000", "--seed", "7"]


def decode(payload: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(x, y, letter index) of the payload's points, as kit/particles.js decodes them."""
    q = np.frombuffer(base64.b64decode(payload["xy"]), dtype="<i2").astype(np.float64) * payload["half"] / 32767
    li = np.frombuffer(base64.b64decode(payload["li"]), dtype=np.uint8)
    return q[0::2], q[1::2], li


def to_texture(payload: dict, rgb: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Texture pixel (column, row) of world points."""
    H, W = rgb.shape[:2]
    return ((x / payload["w"] + 0.5) * W).astype(int).clip(0, W - 1), ((0.5 - y / payload["h"]) * H).astype(int).clip(0, H - 1)


# The size report line of `Written.report`, which `particle-text` prints on stderr.
REPORT = r"text \d+x\d+ px at the end distance, \d+% x \d+% of the 1080x1920 frame"


@pytest.fixture
def no_project():
    """Read the skill's default settings again after a test whose `particle-text` call set a project."""
    yield
    settings.use_project(None)


@pytest.mark.parametrize("font", [TTF, WOFF2], ids=["ttf", "woff2"])
def test_one_line(font: Path) -> None:
    """A word in a TTF and a woff2 font: one letter per non-space character, letter centres left to right, the
    texture's blue channel holding (letter + 1) * 8, every point on the letters' fill and its letter index the
    texture's at its pixel, and the box size from the camera (frame pixels / pixels per world unit). Guards the
    data format kit/particles.js reads (particle_text module docstring)."""
    text = ParticleText(("Ab cd",), font, size=120, count=3000, seed=3)
    rgb, p = text.render()
    assert (p["n"], p["letters"], p["lines"]) == (3000, 4, 1)
    assert p["lc"] == sorted(p["lc"]) and len(set(p["ly"])) == 1
    assert set(np.unique(rgb[..., 2])) == {LETTER_STEP * (k + 1) for k in range(4)}
    H, W = rgb.shape[:2]
    assert p["w"] == pytest.approx(W / SUPERSAMPLE / text.px_per_unit)
    assert p["h"] == pytest.approx(H / SUPERSAMPLE / text.px_per_unit)
    assert p["em"] == pytest.approx(120 / text.px_per_unit)
    x, y, li = decode(p)
    assert len(x) == 3000 and np.abs(x).max() <= p["w"] / 2 and np.abs(y).max() <= p["h"] / 2
    cx, cy = to_texture(p, rgb, x, y)
    assert (rgb[cy, cx, 0] > 0).mean() > 0.97
    assert (rgb[cy, cx, 2] == (li + 1) * LETTER_STEP).mean() > 0.97
    assert set(li) == {0, 1, 2, 3}


def test_two_lines_and_portrait() -> None:
    """Two centred lines on a portrait frame: letters of the first line come first and sit higher (ly), points of
    the top line carry its letters, and the same text on a 1920 px tall frame is 1080/1920 the world size of the
    landscape one. Guards multi-line targets and the camera of `--frame`."""
    lines = ("Two", "lines")
    portrait = ParticleText(lines, TTF, size=150, count=4000, width=1080, height=1920)
    landscape = ParticleText(lines, TTF, size=150, count=4000)
    rgb, p = portrait.render()
    _, q = landscape.render()
    assert (p["letters"], p["lines"]) == (8, 2)
    assert p["ly"][:3] == [p["ly"][0]] * 3 and p["ly"][3:] == [p["ly"][3]] * 5 and p["ly"][0] > p["ly"][3]
    x, y, li = decode(p)
    assert set(li[y > p["ly"][0] - 0.1 * p["em"]]) <= {0, 1, 2}
    assert set(li[y < p["ly"][3] + 0.1 * p["em"]]) <= {3, 4, 5, 6, 7}
    assert p["w"] == pytest.approx(q["w"] * 1080 / 1920)
    assert p["camera"] == {"width": 1080, "height": 1920, "fov": 35.0, "distance": 20.0, "end": 0.9}


def test_seeded_and_written(tmp_path: Path) -> None:
    """write puts <name>_targets.js (setting window.PT_TARGETS[name]) and <name>_tex.png in the directory, the same
    bytes for the same seed and other points for another seed. Guards repeatable files a page can load."""
    a = ParticleText(("Hi",), TTF, count=500, seed=1)
    js, png = a.write("hi", tmp_path / "a")
    a.write("hi", tmp_path / "b")
    ParticleText(("Hi",), TTF, count=500, seed=2).write("hi", tmp_path / "c")
    assert (js.name, png.name) == ("hi_targets.js", "hi_tex.png")
    text = js.read_text()
    assert text.startswith('window.PT_TARGETS = window.PT_TARGETS || {};\nwindow.PT_TARGETS["hi"] = {')
    payload = json.loads(re.search(r"= (\{.*\});\n$", text).group(1))
    assert payload["n"] == 500 and Image.open(png).mode == "RGB"
    assert text == (tmp_path / "b/hi_targets.js").read_text()
    assert text != (tmp_path / "c/hi_targets.js").read_text()


def test_no_leading_slashes() -> None:
    """A point whose Int16 pair encodes to base64 "//" is moved off the front, with its letter index. Guards the
    targets file against the determinism check, which reads a string starting with "//" as a remote URL."""
    xy = np.array([-1, 5, 100, 7, 200, 9], dtype="<i2")
    li = np.array([4, 5, 6], dtype=np.uint8)
    assert base64.b64encode(xy.tobytes()).startswith(b"//")
    out, lo = particle_text._no_leading_slashes(xy, li)
    assert not base64.b64encode(out.tobytes()).startswith(b"//")
    assert out.tolist() == [100, 7, -1, 5, 200, 9] and lo.tolist() == [5, 4, 6]


def test_refusals(tmp_path: Path) -> None:
    """More letters than the texture's blue channel can index, an empty text, a missing font, a non-font file and
    a name that is not an identifier are ValueErrors. Guards the limits of note.md."""
    with pytest.raises(ValueError, match="at most 31"):
        ParticleText(("x" * 32,), TTF)
    with pytest.raises(ValueError, match="no text"):
        ParticleText((" ",), TTF)
    with pytest.raises(ValueError, match="not found"):
        ParticleText(("a",), tmp_path / "none.ttf")
    with pytest.raises(ValueError, match="not a font"):
        ParticleText(("a",), tmp_path / "a.txt")
    with pytest.raises(ValueError, match="name"):
        ParticleText(("a",), TTF, count=10).write("1 bad", tmp_path)
    assert particle_text.default_name(["Two", "lines!"]) == "two_lines"
    assert particle_text.default_name(["2026"]) == "text_2026"
    assert particle_text.parse_frame("1080x1920") == (1080, 1920)


def test_cli_out(tmp_path: Path, no_project) -> None:
    """`particle-text LINE... --font F --frame WxH --out DIR` prints the two files it wrote, named from the text;
    without --scene or --out it is a one-line error. Guards the command line of SKILL.md."""
    done = cli("particle-text", "Two", "lines", "--font", str(WOFF2), "--count", "800", "--frame", "1080x1920",
                   "--out", str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == [str(tmp_path / "two_lines_targets.js"), str(tmp_path / "two_lines_tex.png")]
    assert '"lines": 2' in (tmp_path / "two_lines_targets.js").read_text()
    done = cli("particle-text", "x", "--font", str(TTF), "-p", str(tmp_path))
    assert done.returncode == 1 and "--scene" in done.stderr and "Traceback" not in done.stderr


def test_technique_files_current(tmp_path: Path, no_project) -> None:
    """The technique's title_targets.js and title_tex.png are what its documented command writes now. Guards the
    placeholder files against changes of the generator and of the command's defaults."""
    done = cli("particle-text", *TECHNIQUE_ARGS, "--frame", "1920x1080", "--out", str(tmp_path))
    assert done.returncode == 0, done.stderr
    for name in ("title_targets.js", "title_tex.png"):
        assert (tmp_path / name).read_bytes() == (TECHNIQUE / name).read_bytes(), name


def test_measure_and_fit() -> None:
    """measure gives the ink size in frame pixels at the end distance: the payload's ink times pixels per unit
    over `end`; fitted picks the size at which the ink is the given share of the frame width. Guards the size
    report and `--fit` of `particle-text` (note.md, Another word)."""
    text = ParticleText(("Wide", "text"), TTF, count=200, width=1080, height=1920)
    w, h = text.measure()
    _, p = text.render()
    assert w == pytest.approx(p["ink"][0] * text.px_per_unit / 0.9, rel=1e-6)
    assert h == pytest.approx(p["ink"][1] * text.px_per_unit / 0.9, rel=1e-6)
    fit = text.fitted(0.7)
    assert fit.measure()[0] == pytest.approx(0.7 * 1080, rel=0.01)
    with pytest.raises(ValueError, match="fit"):
        text.fitted(1.5)


def test_write_block_report(tmp_path: Path) -> None:
    """write_block writes <name>_targets.js and <name>_tex.png named from the text; its report gives the text's
    size and share of the frame, warns above 80% of the width, and with `fit` the size is set so the text is that
    share of the width. Guards the size report and `--fit` of `particle-text` (SKILL.md's command table)."""
    text = ParticleText(("Phone",), TTF, size=400, count=300, width=1080, height=1920)
    written = particle_text.write_block(text, tmp_path)
    assert written.files == (tmp_path / "phone_targets.js", tmp_path / "phone_tex.png")
    assert written.too_wide
    report = written.report()
    assert re.search(REPORT, report[0]), report
    assert report[1].startswith("warning: the text is wider than 80%"), report
    fitted = particle_text.write_block(text, tmp_path, fit=0.5)
    assert not fitted.too_wide and len(fitted.report()) == 1
    assert re.search(r" (49|50|51)% x \d+% of the 1080x1920 frame", fitted.report()[0]), fitted.report()


def test_cli_project_frame_and_report(tmp_path: Path, no_project) -> None:
    """With --out, -p naming a portrait project and no --frame, the frame is that project's `video:` size; the
    command reports the text's size and share of the frame on stderr, warns above 80% of the width, and --fit
    sets the size. Guards the default frame and the size report of SKILL.md's command table. The project is
    passed with -p; the default of -p, the current directory, is `config.resolve_project`'s."""
    project = tmp_path / "phone"
    project.mkdir()
    (project / "settings.yaml").write_text("video:\n  width: 1080\n  height: 1920\n  fps: 30\n")
    done = cli("particle-text", "Phone", "--font", str(TTF), "--count", "300", "--size", "400",
               "--out", str(tmp_path / "o"), "-p", str(project))
    assert done.returncode == 0, done.stderr
    assert '"width": 1080, "height": 1920' in (tmp_path / "o/phone_targets.js").read_text()
    assert re.search(REPORT, done.stderr)
    assert "warning: the text is wider than 80%" in done.stderr
    done = cli("particle-text", "Phone", "--font", str(TTF), "--count", "300", "--fit", "0.5",
               "--out", str(tmp_path / "o"), "-p", str(project))
    assert done.returncode == 0 and "warning" not in done.stderr, done.stderr
    assert re.search(r" (49|50|51)% x \d+% of the 1080x1920 frame", done.stderr), done.stderr
