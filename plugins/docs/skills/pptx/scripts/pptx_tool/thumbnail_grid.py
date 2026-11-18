"""Thumbnail grids of slide images, as `visual-preview` writes them.

Every function works on Pillow images and paths, so it runs without LibreOffice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

THUMBNAIL_WIDTH = 300
JPEG_QUALITY = 95
PADDING = 20
BORDER_WIDTH = 2
LABEL_FONT_SIZE_RATIO = 0.12
LABEL_FONTS = ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
OUTLINE_COLOR = (255, 0, 0)
OUTLINE_WIDTH = 5
HIDDEN_SLIDE_COLOR = (200, 200, 200)
HIDDEN_SLIDE_LINE_COLOR = (150, 150, 150)
HIDDEN_SLIDE_LINE_WIDTH = 3


@dataclass(frozen=True)
class TextBox:
    """A text shape's bounding box on its slide, in inches from the top left corner."""
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class SlideSize:
    """Slide width and height in inches."""
    width: float
    height: float


@dataclass(frozen=True)
class Thumbnail:
    """A slide's thumbnail and the 0-based slide index printed above it in the grid."""
    slide_index: int
    image: Image.Image


def _label_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """The first label font of LABEL_FONTS that loads at `size`, else Pillow's default font."""
    for path in LABEL_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


class ThumbnailGridGenerator:
    """Makes slide thumbnails and lays them out in grids of `columns` columns.

    One grid holds at most `columns * (columns + 1)` slides.
    """

    def __init__(self, columns: int):
        self.columns = columns
        self.max_slides_per_grid = columns * (columns + 1)

    def create_hidden_slide_image(self, width: int, height: int) -> Image.Image:
        """Placeholder image for a hidden slide: grey with a diagonal cross."""
        img = Image.new('RGB', (width, height), HIDDEN_SLIDE_COLOR)
        draw = ImageDraw.Draw(img)
        draw.line([(0, 0), (width, height)], fill=HIDDEN_SLIDE_LINE_COLOR, width=HIDDEN_SLIDE_LINE_WIDTH)
        draw.line([(0, height), (width, 0)], fill=HIDDEN_SLIDE_LINE_COLOR, width=HIDDEN_SLIDE_LINE_WIDTH)
        return img

    def draw_text_outlines(self, image: Image.Image, boxes: Sequence[TextBox],
                           slide_size: SlideSize) -> Image.Image:
        """Copy of `image` with a red outline around each text box, scaled from slide inches to pixels."""
        img = image.convert('RGBA')
        draw = ImageDraw.Draw(img)
        img_width, img_height = image.size
        scale_x = img_width / slide_size.width
        scale_y = img_height / slide_size.height
        for box in boxes:
            x = int(box.x * scale_x)
            y = int(box.y * scale_y)
            width = int(box.width * scale_x)
            height = int(box.height * scale_y)
            draw.rectangle([(x, y), (x + width, y + height)], outline=OUTLINE_COLOR, width=OUTLINE_WIDTH)
        return img.convert('RGB')

    def create_thumbnail(self, image: Image.Image) -> Image.Image:
        """`image` resized to THUMBNAIL_WIDTH, keeping its aspect ratio."""
        aspect_ratio = image.height / image.width
        thumb_height = int(THUMBNAIL_WIDTH * aspect_ratio)
        return image.resize((THUMBNAIL_WIDTH, thumb_height), Image.Resampling.LANCZOS)

    def slide_thumbnail(self, image: Image.Image, hidden: bool, boxes: Sequence[TextBox] = (),
                        slide_size: SlideSize | None = None) -> Image.Image:
        """Thumbnail of one rendered slide.

        A hidden slide becomes the placeholder image at the rendered size. Otherwise, when
        `boxes` is not empty, the text boxes are outlined first (`slide_size` is then required).
        """
        if hidden:
            image = self.create_hidden_slide_image(image.width, image.height)
        elif boxes:
            assert slide_size is not None, "slide_size is required to outline text boxes"
            image = self.draw_text_outlines(image, boxes, slide_size)
        return self.create_thumbnail(image)

    def pages(self, thumbnails: Sequence[Thumbnail]) -> list[list[Thumbnail]]:
        """Split `thumbnails` into consecutive grids of at most `max_slides_per_grid` each."""
        step = self.max_slides_per_grid
        return [list(thumbnails[i:i + step]) for i in range(0, len(thumbnails), step)]

    def create_grid(self, thumbnails: Sequence[Thumbnail], output_path: Path) -> None:
        """Lay `thumbnails` out in rows of `columns`, each framed and labelled with its slide index,
        and save the grid as a JPEG at `output_path` (parent directories created). No thumbnails: no file."""
        if not thumbnails:
            return

        rows = (len(thumbnails) + self.columns - 1) // self.columns
        thumb_width = thumbnails[0].image.width
        thumb_height = thumbnails[0].image.height

        font_size = int(thumb_width * LABEL_FONT_SIZE_RATIO)
        font = _label_font(font_size)
        label_height = int(font_size * 1.5)  # space above the frame

        cell_width = thumb_width + 2 * BORDER_WIDTH
        cell_height = label_height + thumb_height + 2 * BORDER_WIDTH
        grid_width = self.columns * cell_width + (self.columns + 1) * PADDING
        grid_height = rows * cell_height + (rows + 1) * PADDING

        grid = Image.new('RGB', (grid_width, grid_height), 'white')
        draw = ImageDraw.Draw(grid)

        for idx, thumbnail in enumerate(thumbnails):
            row = idx // self.columns
            col = idx % self.columns
            x = PADDING + col * (cell_width + PADDING)
            y = PADDING + row * (cell_height + PADDING)

            # Label above the frame
            label = str(thumbnail.slide_index)
            bbox = draw.textbbox((0, 0), label, font=font)
            text_width = bbox[2] - bbox[0]
            draw.text((x + (cell_width - text_width) // 2, y), label, fill='black', font=font)

            # Border around the thumbnail only (below the label)
            frame_y = y + label_height
            draw.rectangle(
                [(x, frame_y), (x + cell_width, frame_y + thumb_height + 2 * BORDER_WIDTH)],
                outline='black',
                width=BORDER_WIDTH
            )
            grid.paste(thumbnail.image, (x + BORDER_WIDTH, frame_y + BORDER_WIDTH))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        grid.save(output_path, 'JPEG', quality=JPEG_QUALITY)
