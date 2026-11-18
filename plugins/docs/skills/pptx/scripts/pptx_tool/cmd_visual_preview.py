"""Generate visual thumbnail grids from PowerPoint presentations.

Converts PPTX slides to images and arranges them in a grid with slide numbers,
optionally highlighting text placeholder regions with red outlines.
"""

import sys
import tempfile
import traceback
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image
from pptx import Presentation
from pptx.presentation import Presentation as PresentationClass

from .cmd_extract_shapes import extract_text
from .common import EMU_PER_INCH, warn
from .exceptions import PptxError
from .slide_render import ImageFormat, render_slides, require_powerpoint
from .thumbnail_grid import SlideSize, TextBox, Thumbnail, ThumbnailGridGenerator

DEFAULT_COLUMNS = 5
MAX_COLUMNS = 6
MIN_COLUMNS = 3
CONVERSION_DPI = 100
PRESENTATION_NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}


def check_preview_input(input_path: Path, columns: int) -> None:
    """Raise PptxError unless `input_path` is an existing PowerPoint file and `columns` is in range."""
    require_powerpoint(input_path)
    if not (MIN_COLUMNS <= columns <= MAX_COLUMNS):
        raise PptxError(f"Columns must be between {MIN_COLUMNS} and {MAX_COLUMNS}")


def default_output_base(input_path: Path) -> Path:
    """Output prefix when none is given: <input dir>/<stem>_thumbnails."""
    return input_path.parent / f"{input_path.stem}_thumbnails"


def grid_output_paths(output_base: Path, num_grids: int) -> list[Path]:
    """Grid file names: <base>.jpg for one grid, else <base>-1.jpg .. <base>-N.jpg."""
    if num_grids == 1:
        return [output_base.with_suffix('.jpg')]
    return [Path(f"{output_base}-{n}.jpg") for n in range(1, num_grids + 1)]


def hidden_slide_indices(pptx_path: Path) -> set[int]:
    """0-based indices of the slides marked hidden (show="0") in ppt/presentation.xml.

    A deck that cannot be read gives an empty set and a warning on stderr.
    """
    hidden = set()
    try:
        with zipfile.ZipFile(pptx_path, 'r') as zip_file:
            root = ET.fromstring(zip_file.read('ppt/presentation.xml'))
        slide_list = root.find('.//p:sldIdLst', PRESENTATION_NS)
        if slide_list is not None:
            for idx, slide in enumerate(slide_list.findall('p:sldId', PRESENTATION_NS)):
                if slide.get('show') == '0':
                    hidden.add(idx)
    except Exception as e:
        warn(f"Could not detect hidden slides: {e}")
    return hidden


def slide_size_inches(prs: PresentationClass) -> SlideSize:
    """Slide width and height of `prs` in inches."""
    width_emu = prs.slide_width
    height_emu = prs.slide_height
    assert width_emu is not None and height_emu is not None, "Slide dimensions cannot be None"
    return SlideSize(width_emu / EMU_PER_INCH, height_emu / EMU_PER_INCH)


def text_boxes_by_slide(pptx_path: Path, prs: PresentationClass) -> dict[int, list[TextBox]]:
    """Bounding boxes of the text shapes of each slide, keyed by 0-based slide index."""
    boxes = {}
    for slide_key, shapes in extract_text(pptx_path, prs).items():
        boxes[int(slide_key.split('-')[1])] = [
            TextBox(shape.left, shape.top, shape.width, shape.height) for shape in shapes.values()
        ]
    return boxes


def visual_preview(input_path: Path, output_base: Path | None = None, columns: int = DEFAULT_COLUMNS,
                   outline_text: bool = False,
                   progress: Callable[[str], None] = lambda _: None) -> list[Path]:
    """Write thumbnail grid JPEGs of the slides of `input_path` and return their paths.

    The grids go to `grid_output_paths(output_base)`; `output_base` defaults to
    `default_output_base(input_path)`. With `outline_text`, text shapes are outlined in red.
    `progress` receives each progress message before its step runs. An invalid input or column
    count raises PptxError; a missing or failing LibreOffice or pdftoppm raises RuntimeError.
    """
    check_preview_input(input_path, columns)
    if output_base is None:
        output_base = default_output_base(input_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        progress(f"Loading presentation: {input_path}")
        prs = Presentation(str(input_path))

        progress(f"Converting {input_path} to images...")
        image_files = render_slides(input_path, Path(temp_dir), CONVERSION_DPI, ImageFormat.JPG)
        hidden = hidden_slide_indices(input_path)

        boxes: dict[int, list[TextBox]] = {}
        slide_size = None
        if outline_text:
            progress("Extracting text placeholder boundaries...")
            boxes = text_boxes_by_slide(input_path, prs)
            slide_size = slide_size_inches(prs)

        progress(f"Processing {len(image_files)} slides...")
        grid_gen = ThumbnailGridGenerator(columns)
        thumbnails = [
            Thumbnail(idx, grid_gen.slide_thumbnail(Image.open(img_file), idx in hidden,
                                                    boxes.get(idx, []), slide_size))
            for idx, img_file in enumerate(image_files)
        ]

        pages = grid_gen.pages(thumbnails)
        output_paths = grid_output_paths(output_base, len(pages))
        for number, (page, output_path) in enumerate(zip(pages, output_paths), start=1):
            progress(f"Creating grid {number}/{len(pages)}...")
            grid_gen.create_grid(page, output_path)
        return output_paths


def run_visual_preview(args) -> int:
    """Entry point from CLI dispatcher."""
    # Input errors print `Error: <message>` through main; any later failure also prints its traceback.
    check_preview_input(args.input, args.cols)
    try:
        output_files = visual_preview(args.input, args.output, args.cols, args.outline_text, progress=print)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
    print(f"\nSuccessfully created {len(output_files)} thumbnail grid(s):")
    for output_file in output_files:
        print(f"  {output_file}")
    return 0
