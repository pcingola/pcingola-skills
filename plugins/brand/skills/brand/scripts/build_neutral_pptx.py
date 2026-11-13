"""Build brands/neutral/pptx/presentation.pptx from the python-pptx default template.

Maintainer script, not a CLI command. Run it from the repository root in the
skill's uv environment, with the `build` dependency group:

    S=plugins/brand/skills/brand/scripts
    (source plugins/brand/lib/uv_env.sh && plugin_env $S &&
     uv run --project $S --group build python $S/build_neutral_pptx.py)

The output is deterministic: the same python-pptx version gives the same bytes.
The template is 16:9 (13.33 x 7.5 in) and holds five layouts and no slides:
"Title Slide", "Section Header", "Title and Content", "Two Content", "Blank".
The theme colour and font schemes come from neutral/brand.yaml.
"""

from __future__ import annotations

import datetime as dt
import io
import sys
import zipfile
from fractions import Fraction
from pathlib import Path

import yaml
from lxml import etree
from pptx import Presentation
from pptx.util import Emu

# build_neutral_pptx.py -> scripts -> <skill>
BRAND_DIR = Path(__file__).resolve().parents[1] / "brands" / "neutral"
OUTPUT = BRAND_DIR / "pptx" / "presentation.pptx"

KEEP_LAYOUTS = ("Title Slide", "Section Header", "Title and Content", "Two Content", "Blank")
SLIDE_WIDTH = Emu(12192000)
SLIDE_HEIGHT = Emu(6858000)
# Fixed zip timestamp, so the bytes do not depend on the build time.
ZIP_DATE = (2026, 1, 1, 0, 0, 0)

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"a": A}

# Theme colour slots, in schema order. Slots the brand does not name keep a
# value derived from the brand colours.
COLOR_SLOTS = ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3",
               "accent4", "accent5", "accent6", "hlink", "folHlink")


def theme_colors(colors: dict[str, str]) -> dict[str, str]:
    """The twelve theme colours as RRGGBB, from the brand colours."""
    defaults = {
        "dk2": colors["accent1"],
        "lt2": colors.get("neutral_chip_fill", "#EFEFF1"),
        "accent4": colors.get("chip_text", "#1F7A72"),
        "accent5": colors.get("caption", "#8A8A90"),
        "accent6": colors.get("neutral_chip_text", "#606068"),
        "hlink": colors["accent2"],
        "folHlink": colors["accent1"],
    }
    out = {}
    for slot in COLOR_SLOTS:
        value = colors.get(slot, defaults.get(slot))
        if value is None:
            raise SystemExit(f"neutral/brand.yaml has no colour {slot}")
        out[slot] = value.lstrip("#").upper()
    return out


def set_theme(theme_xml: bytes, colors: dict[str, str], fonts: dict[str, str]) -> bytes:
    """Replace the colour and font schemes of a theme part."""
    root = etree.fromstring(theme_xml)
    root.set("name", "Neutral")
    scheme = root.find(".//a:clrScheme", NS)
    scheme.set("name", "Neutral")
    for slot, hexval in theme_colors(colors).items():
        el = scheme.find(f"a:{slot}", NS)
        for child in list(el):
            el.remove(child)
        etree.SubElement(el, f"{{{A}}}srgbClr", val=hexval)
    font_scheme = root.find(".//a:fontScheme", NS)
    font_scheme.set("name", "Neutral")
    for tag, role in (("majorFont", "heading"), ("minorFont", "body")):
        latin = font_scheme.find(f"a:{tag}/a:latin", NS)
        latin.set("typeface", fonts[role])
    fmt = root.find(".//a:fmtScheme", NS)
    if fmt is not None:
        fmt.set("name", "Neutral")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def drop_layouts(prs: Presentation) -> None:
    """Remove every layout not in KEEP_LAYOUTS, then order the kept ones."""
    for master in prs.slide_masters:
        layouts = master.slide_layouts
        for layout in list(layouts):
            if layout.name not in KEEP_LAYOUTS:
                layouts.remove(layout)
        # Reorder the layout id list to the order of KEEP_LAYOUTS.
        id_lst = master._element.get_or_add_sldLayoutIdLst()
        by_name = {}
        for entry in list(id_lst):
            layout = master.part.related_slide_layout(entry.rId)
            by_name[layout.name] = entry
            id_lst.remove(entry)
        for name in KEEP_LAYOUTS:
            id_lst.append(by_name[name])
    names = [layout.name for layout in prs.slide_layouts]
    if names != list(KEEP_LAYOUTS):
        raise SystemExit(f"unexpected layouts: {names}")


def widen(part_xml: bytes, factor: Fraction) -> bytes:
    """Scale the x offset and width of every shape in a master or layout part.

    The default template is 4:3 (10 in wide); the placeholders are stretched to
    the 16:9 width. Vertical geometry stays as it is.
    """
    root = etree.fromstring(part_xml)
    for off in root.iterfind(".//a:xfrm/a:off", NS):
        off.set("x", str(round(int(off.get("x")) * factor)))
    for ext in root.iterfind(".//a:xfrm/a:ext", NS):
        ext.set("cx", str(round(int(ext.get("cx")) * factor)))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def drop_all_caps(part_xml: bytes) -> bytes:
    """Remove cap="all" from the run properties of a master or layout part.

    The default Section Header layout sets its title in capitals; the neutral
    titles keep the case of the text.
    """
    root = etree.fromstring(part_xml)
    for tag in ("defRPr", "rPr", "endParaRPr"):
        for el in root.iterfind(f".//a:{tag}[@cap='all']", NS):
            del el.attrib["cap"]
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def set_app(app_xml: bytes) -> bytes:
    """Name the 16:9 format and the theme in the extended properties."""
    text = app_xml.decode("utf-8")
    text = text.replace("On-screen Show (4:3)", "Widescreen")
    text = text.replace("<vt:lpstr>Office Theme</vt:lpstr>", "<vt:lpstr>Neutral</vt:lpstr>")
    return text.encode("utf-8")


def set_size_type(pres_xml: bytes) -> bytes:
    """Drop the 4:3 size type; a 16:9 slide size has none."""
    return pres_xml.replace(b' type="screen4x3"', b"")


def build() -> bytes:
    brand = yaml.safe_load((BRAND_DIR / "brand.yaml").read_text(encoding="utf-8"))
    prs = Presentation()
    factor = Fraction(SLIDE_WIDTH, prs.slide_width)
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT
    if len(prs.slides):
        raise SystemExit("the default template has slides")
    drop_layouts(prs)
    core = prs.core_properties
    core.author = ""
    core.last_modified_by = ""
    core.title = "Neutral"
    core.revision = 1
    fixed = dt.datetime(2026, 1, 1)
    core.created = fixed
    core.modified = fixed
    buf = io.BytesIO()
    prs.save(buf)
    return rewrite(buf.getvalue(), brand["colors"], brand["fonts"], factor)


def rewrite(data: bytes, colors: dict[str, str], fonts: dict[str, str], factor: Fraction) -> bytes:
    """Edit the theme, geometry and properties, then re-zip with fixed timestamps."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename.startswith("ppt/theme/theme") and info.filename.endswith(".xml"):
                body = set_theme(body, colors, fonts)
            elif info.filename.startswith(("ppt/slideMasters/slideMaster", "ppt/slideLayouts/slideLayout")) \
                    and info.filename.endswith(".xml"):
                body = drop_all_caps(widen(body, factor))
            elif info.filename == "docProps/app.xml":
                body = set_app(body)
            elif info.filename == "ppt/presentation.xml":
                body = set_size_type(body)
            member = zipfile.ZipInfo(info.filename, ZIP_DATE)
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = 0o644 << 16
            dst.writestr(member, body)
    return out.getvalue()


def main() -> int:
    data = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(data)
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
