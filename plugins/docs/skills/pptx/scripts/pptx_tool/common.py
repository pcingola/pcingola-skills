"""Constants and input helpers shared across pptx_tool modules."""

import json
from pathlib import Path

from pptx.dml.color import RGBColor

from .exceptions import InvalidIndicesError, PptxError, ValidationError

EMU_PER_INCH = 914400
POINTS_PER_INCH = 72

# scripts/pptx_tool/ -> scripts/ -> <skill root>/assets/
PACKAGE_ROOT = Path(__file__).resolve().parent
ASSETS_ROOT = PACKAGE_ROOT.parent.parent / "assets"
DEFAULT_FONT_PATH = ASSETS_ROOT / "fonts" / "Inter_24pt-Light.ttf"

# Default series/slice colours for add-chart: the accents of the neutral brand
# (brand:brand), then lighter tints of them. Change them here without touching
# the chart code.
CHART_COLORS: tuple[RGBColor, ...] = (
    RGBColor(0x1B, 0x1B, 0x4B),
    RGBColor(0x80, 0x64, 0xA2),
    RGBColor(0x6A, 0xD0, 0xDC),
    RGBColor(0x1F, 0x7A, 0x72),
    RGBColor(0x8A, 0x8A, 0x90),
    RGBColor(0xB3, 0xA2, 0xC7),
    RGBColor(0xA6, 0xE3, 0xEA),
    RGBColor(0x60, 0x60, 0x68),
)



def require_file(path: Path, message: str) -> None:
    """Raise PptxError(message) when `path` does not exist."""
    if not path.exists():
        raise PptxError(message)


def unique_keys(pairs: list[tuple]) -> dict:
    """json object_pairs_hook that rejects a key repeated within one object."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"Duplicate key found in JSON: '{key}'")
        result[key] = value
    return result


def load_data_json(path: Path, label: str) -> dict:
    """Load a command's data JSON file; a missing file or a duplicate key raises PptxError.

    `label` names the file in the not-found message: "<label> JSON file '<path>' not found".
    """
    require_file(path, f"{label} JSON file '{path}' not found")
    with open(path, "r") as f:
        return json.load(f, object_pairs_hook=unique_keys)


def parse_indices(text: str, message: str) -> list[int]:
    """Parse comma-separated slide indices; raise InvalidIndicesError(message) on a non-integer."""
    try:
        return [int(x.strip()) for x in text.split(",")]
    except ValueError:
        raise InvalidIndicesError(message) from None
