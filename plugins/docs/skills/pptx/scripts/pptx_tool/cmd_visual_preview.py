"""Generate visual thumbnail grids from PowerPoint presentations.

Converts PPTX slides to images and arranges them in a grid with slide numbers,
optionally highlighting text placeholder regions with red outlines.
"""

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .cmd_extract_shapes import extract_text
from PIL import Image, ImageDraw, ImageFont

from pptx.presentation import Presentation as PresentationClass
from pptx import Presentation


DEFAULT_COLUMNS = 5
MAX_COLUMNS = 6
MIN_COLUMNS = 3
CONVERSION_DPI = 100
THUMBNAIL_WIDTH = 300
JPEG_QUALITY = 95
PADDING = 20
BORDER_WIDTH = 2
LABEL_FONT_SIZE_RATIO = 0.12
OUTLINE_COLOR = (255, 0, 0)
OUTLINE_WIDTH = 5
HIDDEN_SLIDE_COLOR = (200, 200, 200)
EMU_PER_INCH = 914400

class PPTXConverter:
    """Handles conversion of PPTX to images."""

    def __init__(self, pptx_path: Path, temp_dir: Path):
        self.pptx_path = pptx_path
        self.temp_dir = temp_dir
        self.pdf_path = temp_dir / "presentation.pdf"

    def convert_to_pdf(self) -> None:
        """Convert PPTX to PDF using LibreOffice headless mode."""
        from . import find_libreoffice
        libreoffice = find_libreoffice()
        if not libreoffice:
            raise RuntimeError("LibreOffice is required but not found. Install it: brew install libreoffice (macOS) or apt-get install libreoffice (Linux)")
        cmd = [
            libreoffice,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(self.temp_dir),
            str(self.pptx_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")

        # LibreOffice creates PDF with same base name as input
        generated_pdf = self.temp_dir / f"{self.pptx_path.stem}.pdf"
        if not generated_pdf.exists():
            raise RuntimeError(f"Expected PDF not found: {generated_pdf}")

        generated_pdf.rename(self.pdf_path)

    def convert_to_images(self) -> list[Path]:
        """Convert PDF pages to JPEG images using pdftoppm."""
        if not shutil.which("pdftoppm"):
            raise RuntimeError("pdftoppm (poppler) is required but not found. Install it: brew install poppler (macOS) or apt-get install poppler-utils (Linux)")
        output_prefix = self.temp_dir / "slide"
        cmd = [
            "pdftoppm",
            "-jpeg",
            "-r", str(CONVERSION_DPI),
            str(self.pdf_path),
            str(output_prefix)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pdftoppm conversion failed: {result.stderr}")

        # Collect generated images in order
        image_files = sorted(self.temp_dir.glob("slide-*.jpg"))
        if not image_files:
            raise RuntimeError("No images generated from PDF")

        return image_files


class HiddenSlideDetector:
    """Detects hidden slides in PPTX presentations."""

    def __init__(self, pptx_path: Path, prs: PresentationClass):
        self.pptx_path = pptx_path
        self.prs = prs

    def get_hidden_slides(self) -> set[int]:
        """Return set of zero-based indices of hidden slides."""
        hidden_indices = set()

        try:
            with zipfile.ZipFile(self.pptx_path, 'r') as zip_file:
                # Read presentation.xml to find hidden slides
                pres_xml = zip_file.read('ppt/presentation.xml')
                root = ET.fromstring(pres_xml)

                # Find all slide elements with show="0" attribute
                namespaces = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
                slide_list = root.find('.//p:sldIdLst', namespaces)

                if slide_list is not None:
                    for idx, slide in enumerate(slide_list.findall('p:sldId', namespaces)):
                        if slide.get('show') == '0':
                            hidden_indices.add(idx)
        except Exception as e:
            print(f"Warning: Could not detect hidden slides: {e}", file=sys.stderr)

        return hidden_indices


class PlaceholderExtractor:
    """Extracts text placeholder boundaries from PPTX using extract_text."""

    def __init__(self, pptx_path: Path, prs: PresentationClass):
        self.pptx_path = pptx_path
        self.prs = prs
        self.extracted_data = extract_text(pptx_path, prs)

    def get_slide_dimensions(self) -> tuple[float, float]:
        """Get slide dimensions in inches."""
        width_emu = self.prs.slide_width
        height_emu = self.prs.slide_height
        assert width_emu is not None and height_emu is not None, "Slide dimensions cannot be None"
        return width_emu / EMU_PER_INCH, height_emu / EMU_PER_INCH

    def get_text_shapes(self, slide_index: int) -> list[dict]:
        """Extract text shape boundaries for a specific slide."""
        shapes = []
        slide_key = f"slide-{slide_index}"

        if slide_key not in self.extracted_data:
            return shapes

        for shape_key, shape_data in self.extracted_data[slide_key].items():
            shapes.append({
                'x': shape_data.left,
                'y': shape_data.top,
                'width': shape_data.width,
                'height': shape_data.height
            })

        return shapes


class ThumbnailGridGenerator:
    """Generates thumbnail grids from slide images."""

    def __init__(self, columns: int):
        self.columns = columns
        self.max_slides_per_grid = columns * (columns + 1)

    def create_hidden_slide_image(self, width: int, height: int) -> Image.Image:
        """Create placeholder image for hidden slides."""
        img = Image.new('RGB', (width, height), HIDDEN_SLIDE_COLOR)
        draw = ImageDraw.Draw(img)

        # Draw diagonal cross pattern
        line_color = (150, 150, 150)
        line_width = 3
        draw.line([(0, 0), (width, height)], fill=line_color, width=line_width)
        draw.line([(0, height), (width, 0)], fill=line_color, width=line_width)

        return img

    def draw_text_outlines(self, image: Image.Image, shapes: list[dict],
                          slide_width_inches: float, slide_height_inches: float) -> Image.Image:
        """Draw red outlines around text shapes."""
        img = image.convert('RGBA')
        draw = ImageDraw.Draw(img)

        # Calculate scaling factors
        img_width, img_height = image.size
        scale_x = img_width / slide_width_inches
        scale_y = img_height / slide_height_inches

        # Draw outline for each shape
        for shape in shapes:
            x = int(shape['x'] * scale_x)
            y = int(shape['y'] * scale_y)
            width = int(shape['width'] * scale_x)
            height = int(shape['height'] * scale_y)

            # Draw rectangle outline
            draw.rectangle(
                [(x, y), (x + width, y + height)],
                outline=OUTLINE_COLOR,
                width=OUTLINE_WIDTH
            )

        return img.convert('RGB')

    def create_thumbnail(self, image: Image.Image) -> Image.Image:
        """Resize image to thumbnail size maintaining aspect ratio."""
        aspect_ratio = image.height / image.width
        thumb_height = int(THUMBNAIL_WIDTH * aspect_ratio)
        return image.resize((THUMBNAIL_WIDTH, thumb_height), Image.Resampling.LANCZOS)

    def create_grid(self, thumbnails: list[tuple[int, Image.Image]],
                   output_path: Path) -> None:
        """Create and save a thumbnail grid."""
        if not thumbnails:
            return

        # Calculate grid dimensions
        num_slides = len(thumbnails)
        rows = (num_slides + self.columns - 1) // self.columns

        # Get thumbnail dimensions (all should be same width)
        thumb_width = thumbnails[0][1].width
        thumb_height = thumbnails[0][1].height

        # Calculate font size and label height
        font_size = int(thumb_width * LABEL_FONT_SIZE_RATIO)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except Exception:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()

        # Estimate label height (space above the frame)
        label_height = int(font_size * 1.5)

        # Calculate cell dimensions
        cell_width = thumb_width + 2 * BORDER_WIDTH
        cell_height = label_height + thumb_height + 2 * BORDER_WIDTH

        grid_width = self.columns * cell_width + (self.columns + 1) * PADDING
        grid_height = rows * cell_height + (rows + 1) * PADDING

        # Create grid image
        grid = Image.new('RGB', (grid_width, grid_height), 'white')
        draw = ImageDraw.Draw(grid)

        # Place thumbnails
        for idx, (slide_num, thumbnail) in enumerate(thumbnails):
            row = idx // self.columns
            col = idx % self.columns

            x = PADDING + col * (cell_width + PADDING)
            y = PADDING + row * (cell_height + PADDING)

            # Draw label ABOVE the frame
            label = str(slide_num)
            bbox = draw.textbbox((0, 0), label, font=font)
            text_width = bbox[2] - bbox[0]
            text_x = x + (cell_width - text_width) // 2
            text_y = y
            draw.text((text_x, text_y), label, fill='black', font=font)

            # Draw border around thumbnail only (below the label)
            frame_y = y + label_height
            draw.rectangle(
                [(x, frame_y), (x + cell_width, frame_y + thumb_height + 2 * BORDER_WIDTH)],
                outline='black',
                width=BORDER_WIDTH
            )

            # Paste thumbnail inside the frame
            thumb_x = x + BORDER_WIDTH
            thumb_y = frame_y + BORDER_WIDTH
            grid.paste(thumbnail, (thumb_x, thumb_y))

        # Save grid
        output_path.parent.mkdir(parents=True, exist_ok=True)
        grid.save(output_path, 'JPEG', quality=JPEG_QUALITY)


def run_visual_preview(args) -> None:
    """Entry point from CLI dispatcher."""
    # Validate input
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if args.input.suffix.lower() not in ['.pptx', '.ppt']:
        print(f"Error: Input must be a PowerPoint file (.pptx or .ppt)", file=sys.stderr)
        sys.exit(1)

    if not (MIN_COLUMNS <= args.cols <= MAX_COLUMNS):
        print(f"Error: Columns must be between {MIN_COLUMNS} and {MAX_COLUMNS}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_base = args.output
    else:
        output_base = args.input.parent / f"{args.input.stem}_thumbnails"

    # Create temporary directory for intermediate files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # Load presentation
            print(f"Loading presentation: {args.input}")
            prs = Presentation(str(args.input))

            # Convert PPTX to images
            print(f"Converting {args.input} to images...")
            converter = PPTXConverter(args.input, temp_path)
            converter.convert_to_pdf()
            image_files = converter.convert_to_images()

            # Detect hidden slides
            hidden_detector = HiddenSlideDetector(args.input, prs)
            hidden_slides = hidden_detector.get_hidden_slides()

            # Extract text shapes if outlining is enabled
            placeholder_extractor = None
            slide_width_inches = 10.0
            slide_height_inches = 7.5

            if args.outline_text:
                print("Extracting text placeholder boundaries...")
                placeholder_extractor = PlaceholderExtractor(args.input, prs)
                slide_width_inches, slide_height_inches = placeholder_extractor.get_slide_dimensions()

            # Load and process images
            print(f"Processing {len(image_files)} slides...")
            thumbnails = []
            grid_gen = ThumbnailGridGenerator(args.cols)

            for idx, img_file in enumerate(image_files):
                if idx in hidden_slides:
                    # Create placeholder for hidden slide
                    sample_img = Image.open(img_file)
                    hidden_img = grid_gen.create_hidden_slide_image(
                        sample_img.width, sample_img.height
                    )
                    image = hidden_img
                else:
                    image = Image.open(img_file)

                    # Draw text outlines if requested
                    if args.outline_text and placeholder_extractor:
                        shapes = placeholder_extractor.get_text_shapes(idx)
                        if shapes:
                            image = grid_gen.draw_text_outlines(
                                image, shapes, slide_width_inches, slide_height_inches
                            )

                # Create thumbnail
                thumbnail = grid_gen.create_thumbnail(image)
                thumbnails.append((idx, thumbnail))

            # Generate grids
            num_grids = (len(thumbnails) + grid_gen.max_slides_per_grid - 1) // grid_gen.max_slides_per_grid

            output_files = []
            for grid_idx in range(num_grids):
                start_idx = grid_idx * grid_gen.max_slides_per_grid
                end_idx = min(start_idx + grid_gen.max_slides_per_grid, len(thumbnails))
                grid_thumbnails = thumbnails[start_idx:end_idx]

                # Determine output filename
                if num_grids == 1:
                    output_path = output_base.with_suffix('.jpg')
                else:
                    output_path = Path(f"{output_base}-{grid_idx + 1}.jpg")

                print(f"Creating grid {grid_idx + 1}/{num_grids}...")
                grid_gen.create_grid(grid_thumbnails, output_path)
                output_files.append(output_path)

            # Print summary
            print(f"\nSuccessfully created {num_grids} thumbnail grid(s):")
            for output_file in output_files:
                print(f"  {output_file}")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)
