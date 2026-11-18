"""Helpers for pptx integration tests."""

import contextlib
import io
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

from tests.options import keep_tmp

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PROJECT_DIR / "tests" / "data"
TMP_DIR = DATA_DIR / "tmp_pptx"
PPTX_TOOL = str(PROJECT_DIR / "plugins" / "docs" / "skills" / "pptx" / "scripts" / "pptx.sh")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PPTX_TOOL, *args], capture_output=True, text=True, cwd=PROJECT_DIR, timeout=25)


@dataclass(frozen=True)
class CliResult:
    """Exit code and captured output of one in-process CLI call."""

    returncode: int
    stdout: str
    stderr: str


def cli(*argv: str) -> CliResult:
    """Run the pptx CLI's `main(argv)` in process, capturing stdout and stderr.

    For tests whose subject is CLI behaviour: argument parsing, defaults, the
    output format and the exit code. Tests of a command's logic call its core
    function instead.
    """
    from pptx_tool.pptx import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return CliResult(code, out.getvalue(), err.getvalue())


def has_libreoffice() -> bool:
    """Whether LibreOffice is installed — export-slides and visual-preview need it.

    The guard keeps the pptx integration suite runnable on a machine without
    LibreOffice.
    """
    from pptx_tool import find_libreoffice
    return find_libreoffice() is not None


def fresh_dir(name: str) -> Path:
    """Create (or recreate) a subdirectory under TMP_DIR and return its path."""
    d = TMP_DIR / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


def cleanup_dir(d: Path) -> None:
    if not keep_tmp():
        shutil.rmtree(d, ignore_errors=True)


def create_test_pptx(d: Path, name: str = "test.pptx", num_slides: int = 3,
                     add_text: bool = True, add_placeholders: bool = False) -> Path:
    """Create a simple test PPTX with the given number of slides.

    Each slide gets a title and optional body text. If add_placeholders is True,
    picture placeholders are added (using the blank layout approach).
    """
    prs = Presentation()
    # Use the title+content layout (index 1) for text shapes
    layout = prs.slide_layouts[1]

    for i in range(num_slides):
        slide = prs.slides.add_slide(layout)
        # Set title
        slide.shapes.title.text = f"Slide {i} Title"
        if add_text:
            # Body placeholder is typically index 1
            body = slide.placeholders[1]
            body.text = f"Content for slide {i}"

    path = d / name
    prs.save(str(path))
    return path


def _clone_placeholder(slide, placeholder, new_idx: int, dx_inches: float):
    """Duplicate a placeholder on the same slide under a new idx, shifted right.

    The stock python-pptx template has no layout carrying two PICTURE
    placeholders, and `add-images` with two images needs two. Cloning the
    element builds that shape without shipping a template file; see
    create_multilayout_pptx.
    """
    from copy import deepcopy

    el = deepcopy(placeholder._element)
    nv_pr = el.find(qn("p:nvSpPr")).find(qn("p:cNvPr"))
    nv_pr.set("id", str(1000 + new_idx))
    nv_pr.set("name", f"{nv_pr.get('name')} {new_idx}")
    ph = el.find(qn("p:nvSpPr")).find(qn("p:nvPr")).find(qn("a:ph")) \
        if el.find(qn("p:nvSpPr")).find(qn("p:nvPr")).find(qn("a:ph")) is not None \
        else el.find(qn("p:nvSpPr")).find(qn("p:nvPr")).find(qn("p:ph"))
    ph.set("idx", str(new_idx))
    slide.shapes._spTree.append(el)
    clone = slide.shapes[-1]
    clone.left = placeholder.left + Inches(dx_inches)
    clone.top = placeholder.top
    clone.width = placeholder.width
    clone.height = placeholder.height
    return clone


def create_multilayout_pptx(d: Path, name: str = "multilayout.pptx") -> Path:
    """Build a synthetic multi-layout fixture deck from the stock python-pptx theme:

      slide 0  Title and Content   — TITLE + one OBJECT placeholder
      slide 1  Picture with Caption — two PICTURE placeholders (second cloned)
      slide 2  Two Content         — two OBJECT placeholders
      slide 3  Title Only          — plus a deliberately overlong text box, so
                                     `extract-shapes --issues-only` has something
                                     to flag
      slide 4  Blank               — a 2x2 table and speaker notes

    Slide size is set to 13.33 x 7.5 in (16:9).
    """
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 0 — title + OBJECT
    s0 = prs.slides.add_slide(prs.slide_layouts[1])
    s0.shapes.title.text = "Multilayout Deck"
    s0.placeholders[1].text_frame.text = "An OBJECT placeholder holding body text"

    # 1 — two PICTURE placeholders
    s1 = prs.slides.add_slide(prs.slide_layouts[8])
    s1.shapes.title.text = "Picture Slide"
    picture_ph = next(
        p for p in s1.placeholders if p.placeholder_format.type == PP_PLACEHOLDER.PICTURE
    )
    _clone_placeholder(s1, picture_ph, new_idx=20, dx_inches=4.5)

    # 2 — two OBJECT placeholders
    s2 = prs.slides.add_slide(prs.slide_layouts[3])
    s2.shapes.title.text = "Two Content"
    for ph in s2.placeholders:
        if ph.placeholder_format.type == PP_PLACEHOLDER.OBJECT:
            ph.text_frame.text = "column text"

    # 3 — deliberate overflow: ~90 words at 18pt in a 1.5 x 0.4 in box
    s3 = prs.slides.add_slide(prs.slide_layouts[5])
    s3.shapes.title.text = "Overflow"
    box = s3.shapes.add_textbox(Inches(1), Inches(3), Inches(1.5), Inches(0.4))
    box.text_frame.word_wrap = True
    box.text_frame.text = " ".join(["overflowing"] * 90)

    # 4 — table + speaker notes, no text shapes of its own
    s4 = prs.slides.add_slide(prs.slide_layouts[6])
    table = s4.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(6), Inches(2)).table
    table.cell(0, 0).text = "Region"
    table.cell(0, 1).text = "Revenue"
    table.cell(1, 0).text = "EMEA"
    table.cell(1, 1).text = "$45M"
    s4.notes_slide.notes_text_frame.text = "Talk track: emphasise EMEA growth."

    path = d / name
    prs.save(str(path))
    return path


def create_test_image(d: Path, name: str = "test_image.png",
                      width: int = 100, height: int = 100,
                      color: str = "red") -> Path:
    """Create a simple test image."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=color)
    path = d / name
    img.save(path)
    return path


def create_pptx_with_table_and_image(d: Path, name: str = "with_media.pptx") -> Path:
    """Build a 2-slide PPTX: slide 1 has a title + image, slide 2 has a table."""
    from PIL import Image as PILImage

    img_path = d / "_probe.png"
    PILImage.new("RGB", (200, 120), color=(20, 140, 220)).save(img_path)

    prs = Presentation()
    blank_layout = prs.slide_layouts[5]  # Title only

    slide1 = prs.slides.add_slide(blank_layout)
    slide1.shapes.title.text = "Image Slide"
    slide1.shapes.add_picture(
        str(img_path),
        left=Inches(1),
        top=Inches(2),
        width=Inches(4),
        height=Inches(3),
    )

    slide2 = prs.slides.add_slide(blank_layout)
    slide2.shapes.title.text = "Table Slide"
    rows, cols = 3, 3
    table_shape = slide2.shapes.add_table(
        rows, cols, Inches(1), Inches(2), Inches(7), Inches(3)
    )
    table = table_shape.table
    headers = ["Name", "Value", "Unit"]
    body = [["Alpha", "1.0", "kg"], ["Beta", "2.5", "kg"]]
    data = [headers, *body]
    for r in range(rows):
        for c in range(cols):
            table.cell(r, c).text = data[r][c]

    path = d / name
    prs.save(str(path))
    img_path.unlink(missing_ok=True)
    return path


def stamp_description(pptx_path: Path, description: str) -> None:
    """Insert a summary slide at position 0 describing what to expect.

    Only applies with `pytest --keep-tmp`. The summary slide has a light grey background
    with the test name, file name, and a checklist of expected outcomes so the
    reviewer can verify the presentation without reading the test code.
    """
    if not keep_tmp() or not pptx_path.exists():
        return

    from pptx.oxml.ns import qn

    prs = Presentation(str(pptx_path))
    slide_count = len(prs.slides)
    if slide_count == 0:
        return

    # Use the blank layout (last layout, or first with no placeholders)
    blank_layout = prs.slide_layouts[-1]
    for layout in prs.slide_layouts:
        if len(layout.placeholders) == 0:
            blank_layout = layout
            break

    summary_slide = prs.slides.add_slide(blank_layout)

    # Remove any default placeholder shapes from the blank slide
    for shape in list(summary_slide.shapes):
        shape.element.getparent().remove(shape.element)

    # Set light grey background
    bg = summary_slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(0xF2, 0xF2, 0xF2)

    margin = Inches(0.5)
    content_width = prs.slide_width - 2 * margin

    # Header: "TEST SUMMARY"
    header_box = summary_slide.shapes.add_textbox(margin, Inches(0.4), content_width, Inches(0.5))
    tf = header_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "TEST SUMMARY"
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # File name
    file_box = summary_slide.shapes.add_textbox(margin, Inches(1.0), content_width, Inches(0.4))
    tf = file_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = f"File: {pptx_path.name}    |    Content slides: {slide_count}"
    p.font.size = Pt(14)
    p.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # Description body — split on newlines for multi-line descriptions
    desc_box = summary_slide.shapes.add_textbox(
        margin, Inches(1.6), content_width, prs.slide_height - Inches(2.2),
    )
    tf = desc_box.text_frame
    tf.word_wrap = True

    lines = description.strip().split("\n")
    for i, line in enumerate(lines):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = line.strip()
        p.font.size = Pt(14)
        p.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
        p.space_after = Pt(4)

    # Move the summary slide to position 0
    # python-pptx appends new slides at the end; we move it to the front
    sldIdLst = prs.slides._sldIdLst
    last_entry = list(sldIdLst)[-1]
    sldIdLst.remove(last_entry)
    sldIdLst.insert(0, last_entry)

    prs.save(str(pptx_path))


def write_readme(d: Path, description: str) -> None:
    """Write a README.txt in directory *d* describing the test outputs.

    Only applies with `pytest --keep-tmp`. Use this for tests whose outputs are not
    PPTX files (JSON, PDF, JPEG, stdout-only) and therefore cannot carry a
    stamp_description slide.
    """
    if not keep_tmp():
        return
    readme = d / "README.txt"
    readme.write_text(description.strip() + "\n")


def write_text_data_json(d: Path, data: dict, name: str = "text_data.json") -> Path:
    """Write a text data JSON file for use with add-text command."""
    path = d / name
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path
