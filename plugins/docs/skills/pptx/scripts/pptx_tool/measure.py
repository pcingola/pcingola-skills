"""The one font-loading and text-measurement path in the package.

Overflow detection (`cmd_extract_shapes`) and the font-size fitter
(`text_fitting`) both measure through here, so a shape cannot be reported as
overflowing by one and fitting by the other. What it does:

- it searches LibreOffice's bundled fonts and maps MS names to the
  metric-compatible clones LibreOffice actually substitutes (Calibri ->
  Carlito), so widths match what the renderer will produce;
- it prefers an exact filename match, then penalises style tokens the caller did
  not ask for, so "Calibri" does not silently measure Carlito-Bold;
- its fallback estimate scales with font size, so 10pt and 32pt text do not
  get the same line count;
- it applies a 10% width margin and counts the extra lines a word wider than the
  column forces, which is closer to how PowerPoint wraps than a plain word wrap.

When no system font matches, the bundled Inter face in `assets/fonts/` is used
before PIL's built-in default. That is what `assets/fonts/` is for: PIL's
default is a bitmap font whose metrics have nothing to do with the deck, so
falling through to it degrades every measurement silently while every assertion
still passes.
"""

import platform
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import DEFAULT_FONT_PATH

DPI = 96  # PIL renders at 96 DPI; inches = pixels / DPI
POINTS_PER_INCH = 72

# Single shared font cache and measuring surface for the whole package.
_FONT_CACHE: dict[tuple[str, int], "ImageFont.ImageFont"] = {}
_MEASURE_DRAW = ImageDraw.Draw(Image.new("RGB", (1, 1)))

# MS fonts LibreOffice renders via metric-compatible clones. When the named MS
# font isn't installed, LibreOffice substitutes the clone -- so measuring the
# clone here keeps PIL's widths matched to the actual rendered output.
_FONT_ALIASES = {
    "calibri": "Carlito",
    "cambria": "Caladea",
    "cambria math": "Caladea",
}


def _libreoffice_font_dirs() -> list[Path]:
    """LibreOffice's bundled TrueType fonts (Carlito, Caladea, ...)."""
    candidates = [
        Path("/Applications/LibreOffice.app/Contents/Resources/fonts/truetype"),  # macOS
        Path("/usr/lib/libreoffice/share/fonts/truetype"),                        # Linux
        Path("/opt/libreoffice/share/fonts/truetype"),
        Path("C:/Program Files/LibreOffice/share/fonts/truetype"),                # Windows
    ]
    return [d for d in candidates if d.exists()]


def _system_font_dirs() -> list[Path]:
    """System font directories based on OS, plus LibreOffice's bundled fonts."""
    system = platform.system()
    if system == "Darwin":
        dirs = [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library" / "Fonts"]
    elif system == "Linux":
        dirs = [Path("/usr/share/fonts/truetype"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
    else:
        dirs = [Path("C:/Windows/Fonts")]
    return dirs + _libreoffice_font_dirs()


def _find_font_file(font_dir: Path, font_name: str) -> Path | None:
    """Find a font file with fuzzy name matching, preferring the closest variant.

    An exact stem match wins; otherwise the shortest matching stem, so a request
    for "Arial" picks "Arial.ttf" over a decorated "Arial Narrow Italic.ttf"
    whose metrics would missize a text-fitted shape.
    """
    if not font_dir.exists():
        return None

    normalized_name = font_name.lower().replace(" ", "").replace("-", "")

    matches = []
    for ext in [".ttf", ".otf", ".TTF", ".OTF"]:
        for font_file in font_dir.rglob(f"*{ext}"):
            file_name = font_file.stem.lower().replace(" ", "").replace("-", "")
            if normalized_name in file_name or file_name in normalized_name:
                if file_name == normalized_name:
                    return font_file
                matches.append((font_file, file_name))
    if not matches:
        return None
    # Prefer the plain/regular weight: penalize style tokens the request didn't
    # ask for (so "Calibri" picks Carlito-Regular, not Carlito-Bold), then take
    # the shortest remaining stem.
    style_tokens = ("bold", "italic", "oblique", "narrow", "light", "black",
                    "condensed", "semibold", "medium", "thin", "heavy")

    def rank(file_name: str):
        extra = file_name.replace(normalized_name, "")
        penalty = sum(1 for t in style_tokens if t in extra)
        return (penalty, len(file_name))

    return min(matches, key=lambda m: rank(m[1]))[0]


def load_bundled_font(font_size: float) -> "ImageFont.ImageFont | None":
    """Load the Inter face shipped in assets/fonts/, or None if it is missing."""
    try:
        return ImageFont.truetype(str(DEFAULT_FONT_PATH), int(font_size))
    except Exception:
        return None


def load_font(font_name: str, font_size: float):
    """Load a TrueType font (fuzzy-matched by name), cached package-wide.

    Falls back to the bundled Inter face, then to PIL's default.
    """
    cache_key = (font_name, int(font_size))
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    names_to_try = [font_name]
    alias = _FONT_ALIASES.get(font_name.lower())
    if alias:
        names_to_try.append(alias)

    font = None
    try:
        dirs = _system_font_dirs()
        for name in names_to_try:
            for font_dir in dirs:
                font_path = _find_font_file(font_dir, name)
                if font_path:
                    font = ImageFont.truetype(str(font_path), int(font_size))
                    break
            if font is not None:
                break
    except Exception:
        font = None

    if font is None:
        # A real outline face beats PIL's bitmap default, whose metrics have
        # nothing to do with the deck. This is why assets/fonts/ ships.
        font = load_bundled_font(font_size)

    if font is None:
        # Scalable default (Pillow >=10.1) so width still tracks size, unlike the
        # bare fixed-size default which silently under-measures large text.
        try:
            font = ImageFont.load_default(int(font_size))
        except TypeError:
            font = ImageFont.load_default()

    _FONT_CACHE[cache_key] = font
    return font


def text_width(text: str, font_name: str, font_size: float) -> float:
    """Rendered width of a single line of text, in inches.

    This is the one text-width measurement in the codebase — callers that place
    shapes by text width (e.g. `chip_row`) reuse it rather than rolling a second
    measurer.
    """
    if not text:
        return 0.0
    # PIL's truetype size is in pixels; a point size renders at font_size*DPI/72 px
    # at 96 DPI. Loading at the raw point value would under-measure by 72/96.
    font = load_font(font_name, font_size * DPI / POINTS_PER_INCH)
    return _MEASURE_DRAW.textlength(text, font=font) / DPI


def measure_text_lines(text: str, font_name: str, font_size: float, width_inches: float) -> int:
    """Estimate how many wrapped lines `text` occupies in a column `width_inches` wide."""
    try:
        font = load_font(font_name, font_size)
        draw = _MEASURE_DRAW

        words = text.split()
        if not words:
            return 1

        width_pixels = width_inches * DPI * 0.9  # 10% safety margin

        lines = 1
        current_line = words[0]

        for word in words[1:]:
            test_line = current_line + " " + word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]

            if line_width <= width_pixels:
                current_line = test_line
            else:
                lines += 1
                current_line = word

                # A single word wider than the column wraps onto further lines.
                bbox = draw.textbbox((0, 0), word, font=font)
                word_width = bbox[2] - bbox[0]
                if word_width > width_pixels:
                    lines += int(word_width / width_pixels)

        return lines

    except Exception:
        # Fallback estimate — scales with font size, unlike a fixed chars-per-inch.
        chars_per_inch = POINTS_PER_INCH / font_size * 2.5
        chars_per_line = max(1, int(width_inches * chars_per_inch))
        return max(1, (len(text) + chars_per_line - 1) // chars_per_line)
