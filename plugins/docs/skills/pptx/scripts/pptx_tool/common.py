"""Constants shared across pptx_tool modules."""

from pathlib import Path

from pptx.dml.color import RGBColor

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

