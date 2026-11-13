"""Formatting classes for paragraph and text run operations."""

from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt


class ParagraphFormatter:
    """Handles paragraph-level formatting operations."""

    ALIGNMENT_MAP = {
        "LEFT": PP_ALIGN.LEFT,
        "CENTER": PP_ALIGN.CENTER,
        "RIGHT": PP_ALIGN.RIGHT,
        "JUSTIFY": PP_ALIGN.JUSTIFY,
    }

    @staticmethod
    def clear_bullets(paragraph) -> OxmlElement:
        """Remove all bullet formatting elements from a paragraph.

        Returns:
            The paragraph properties element (pPr)
        """
        pPr = paragraph._element.get_or_add_pPr()

        bullet_tags = ["buChar", "buNone", "buAutoNum", "buFont"]
        for child in list(pPr):
            tag_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag_name in bullet_tags:
                pPr.remove(child)

        return pPr

    @staticmethod
    def apply_bullet_formatting(paragraph, properties: dict, pPr: OxmlElement) -> None:
        """Apply bullet formatting to a paragraph.

        Args:
            paragraph: PowerPoint paragraph object
            properties: Dictionary containing bullet properties (level, font_size)
            pPr: Paragraph properties XML element
        """
        level = properties.get("level", 0)
        paragraph.level = level

        font_size = properties.get("font_size", 18.0)
        level_indent_emu = int((font_size * (1.6 + level * 1.6)) * 12700)
        hanging_indent_emu = int(-font_size * 0.8 * 12700)

        pPr.attrib["marL"] = str(level_indent_emu)
        pPr.attrib["indent"] = str(hanging_indent_emu)

        buChar = OxmlElement("a:buChar")
        buChar.set("char", "\u2022")
        pPr.append(buChar)

        if "alignment" not in properties:
            paragraph.alignment = PP_ALIGN.LEFT

    @staticmethod
    def remove_bullet_formatting(pPr: OxmlElement) -> None:
        """Remove bullet formatting and reset indentation.

        Args:
            pPr: Paragraph properties XML element
        """
        pPr.attrib["marL"] = "0"
        pPr.attrib["indent"] = "0"

        buNone = OxmlElement("a:buNone")
        pPr.insert(0, buNone)

    @staticmethod
    def apply_alignment(paragraph, alignment_name: str) -> None:
        """Apply text alignment to a paragraph.

        Args:
            paragraph: PowerPoint paragraph object
            alignment_name: Alignment name (LEFT, CENTER, RIGHT, JUSTIFY)
        """
        if alignment_name in ParagraphFormatter.ALIGNMENT_MAP:
            paragraph.alignment = ParagraphFormatter.ALIGNMENT_MAP[alignment_name]

    @staticmethod
    def apply_spacing(paragraph, properties: dict) -> None:
        """Apply spacing properties to a paragraph.

        Args:
            paragraph: PowerPoint paragraph object
            properties: Dictionary containing spacing properties
        """
        if "space_before" in properties:
            paragraph.space_before = Pt(properties["space_before"])
        if "space_after" in properties:
            paragraph.space_after = Pt(properties["space_after"])
        if "line_spacing" in properties:
            paragraph.line_spacing = Pt(properties["line_spacing"])


class TextRunFormatter:
    """Handles text run-level formatting operations."""

    @staticmethod
    def apply_font_properties(run, properties: dict) -> None:
        """Apply font properties to a text run.

        Args:
            run: PowerPoint text run object
            properties: Dictionary containing font properties
        """
        if "bold" in properties:
            run.font.bold = properties["bold"]
        if "italic" in properties:
            run.font.italic = properties["italic"]
        if "underline" in properties:
            run.font.underline = properties["underline"]
        if "font_size" in properties:
            run.font.size = Pt(properties["font_size"])
        if "font_name" in properties:
            run.font.name = properties["font_name"]

        # Strikethrough
        if "strikethrough" in properties:
            try:
                rPr = run.font._element.get_or_add_rPr()
                rPr.set("strike", "sngStrike" if properties["strikethrough"] else "noStrike")
            except Exception:
                pass

        # Superscript / subscript
        if "superscript" in properties and properties["superscript"]:
            try:
                rPr = run.font._element.get_or_add_rPr()
                rPr.set("baseline", "30000")
            except Exception:
                pass
        elif "subscript" in properties and properties["subscript"]:
            try:
                rPr = run.font._element.get_or_add_rPr()
                rPr.set("baseline", "-25000")
            except Exception:
                pass
        elif "superscript" in properties or "subscript" in properties:
            try:
                rPr = run.font._element.get_or_add_rPr()
                if "baseline" in rPr.attrib:
                    del rPr.attrib["baseline"]
            except Exception:
                pass

        # All caps
        if "all_caps" in properties:
            try:
                run.font.all_caps = properties["all_caps"]
            except Exception:
                pass

        # Small caps
        if "small_caps" in properties:
            try:
                rPr = run.font._element.get_or_add_rPr()
                rPr.set("smCaps", "1" if properties["small_caps"] else "0")
            except Exception:
                pass

        # Character spacing
        if "char_spacing" in properties and properties["char_spacing"] is not None:
            try:
                rPr = run.font._element.get_or_add_rPr()
                rPr.set("spc", str(int(properties["char_spacing"] * 100)))
            except Exception:
                pass

        TextRunFormatter._apply_color(run, properties)

    @staticmethod
    def _apply_color(run, properties: dict) -> None:
        """Apply color properties to a text run.

        Args:
            run: PowerPoint text run object
            properties: Dictionary containing color properties
        """
        if "color" in properties:
            color_hex = properties["color"].lstrip("#")
            if len(color_hex) == 6:
                r = int(color_hex[0:2], 16)
                g = int(color_hex[2:4], 16)
                b = int(color_hex[4:6], 16)
                run.font.color.rgb = RGBColor(r, g, b)
        elif "theme_color" in properties:
            theme_name = properties["theme_color"]
            try:
                run.font.color.theme_color = getattr(MSO_THEME_COLOR, theme_name)
            except AttributeError:
                print(f"  WARNING: Unknown theme color '{theme_name}'")


class ParagraphProcessor:
    """Processes paragraph text additions with formatting."""

    def __init__(self):
        self.para_formatter = ParagraphFormatter()
        self.run_formatter = TextRunFormatter()

    def apply_properties(self, paragraph, properties: dict, override_font_size: float | None = None) -> None:
        """Apply all formatting properties to a paragraph.

        Args:
            paragraph: PowerPoint paragraph object
            properties: Dictionary containing paragraph and font properties
            override_font_size: If provided, overrides the font_size in properties (used for auto-fitting)
        """
        text = properties.get("text", "")

        # Create effective properties with font size override if provided
        effective_properties = properties.copy()
        if override_font_size is not None:
            effective_properties["font_size"] = override_font_size

        pPr = self.para_formatter.clear_bullets(paragraph)

        if effective_properties.get("bullet", False):
            self.para_formatter.apply_bullet_formatting(paragraph, effective_properties, pPr)
        else:
            self.para_formatter.remove_bullet_formatting(pPr)

        if "alignment" in effective_properties:
            self.para_formatter.apply_alignment(paragraph, effective_properties["alignment"])

        self.para_formatter.apply_spacing(paragraph, effective_properties)

        if not paragraph.runs:
            run = paragraph.add_run()
            run.text = text
        else:
            run = paragraph.runs[0]
            run.text = text

        self.run_formatter.apply_font_properties(run, effective_properties)


class ShapeFormatter:
    """Handles shape-level formatting: fill, border/line, text frame properties."""

    @staticmethod
    def apply_fill(shape, properties: dict) -> None:
        """Apply fill to a shape.

        Supported keys: fill_type ("SOLID","BACKGROUND","NONE"), fill_color ("#RRGGBB"),
        fill_theme_color (theme slot name e.g. "ACCENT_1").
        """
        fill_type = properties.get("fill_type")
        if fill_type is None:
            return
        try:
            fill = shape.fill
            if fill_type in ("BACKGROUND", "NONE"):
                fill.background()
            elif fill_type == "SOLID":
                fill.solid()
                color = properties.get("fill_color")
                theme_color = properties.get("fill_theme_color")
                if color:
                    h = color.lstrip("#")
                    fill.fore_color.rgb = RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                elif theme_color:
                    try:
                        fill.fore_color.theme_color = getattr(MSO_THEME_COLOR, theme_color)
                    except AttributeError:
                        print(f"  WARNING: Unknown theme color '{theme_color}'")
        except Exception as e:
            print(f"  WARNING: Could not apply fill: {e}")

    @staticmethod
    def apply_border(shape, properties: dict) -> None:
        """Apply line/border to a shape.

        Supported keys: border_visible (bool), border_color ("#RRGGBB"),
        border_theme_color, border_weight_pt (float), border_dash (str).
        """
        border_visible = properties.get("border_visible")
        if border_visible is None:
            return
        try:
            line = shape.line
            if not border_visible:
                line.fill.background()
                return
            color = properties.get("border_color")
            theme_color = properties.get("border_theme_color")
            weight = properties.get("border_weight_pt")
            dash = properties.get("border_dash")
            if color:
                h = color.lstrip("#")
                line.color.rgb = RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            elif theme_color:
                try:
                    line.color.theme_color = getattr(MSO_THEME_COLOR, theme_color)
                except AttributeError:
                    print(f"  WARNING: Unknown theme color '{theme_color}'")
            if weight is not None:
                line.width = Pt(weight)
            if dash:
                from pptx.enum.dml import MSO_LINE_DASH_STYLE
                try:
                    line.dash_style = getattr(MSO_LINE_DASH_STYLE, dash.upper())
                except AttributeError:
                    print(f"  WARNING: Unknown dash style '{dash}'")
        except Exception as e:
            print(f"  WARNING: Could not apply border: {e}")

    @staticmethod
    def apply_text_frame_properties(shape, properties: dict) -> None:
        """Apply text frame properties.

        Supported keys: word_wrap (bool), autofit ("NONE"/"TEXT_TO_FIT_SHAPE"/"SHAPE_TO_FIT_TEXT"),
        text_margin_top/left/bottom/right (inches), vertical_alignment ("TOP"/"MIDDLE"/"BOTTOM").
        """
        if not hasattr(shape, "has_text_frame") or not shape.has_text_frame:
            return
        tf = shape.text_frame

        if "word_wrap" in properties and properties["word_wrap"] is not None:
            try:
                tf.word_wrap = properties["word_wrap"]
            except Exception:
                pass

        if "autofit" in properties and properties["autofit"] is not None:
            try:
                from pptx.enum.text import MSO_AUTO_SIZE
                autofit_map = {
                    "NONE": MSO_AUTO_SIZE.NONE,
                    "TEXT_TO_FIT_SHAPE": MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE,
                    "SHAPE_TO_FIT_TEXT": MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT,
                }
                val = autofit_map.get(properties["autofit"].upper())
                if val is not None:
                    tf.auto_size = val
            except Exception:
                pass

        for attr, key in [
            ("margin_top", "text_margin_top"),
            ("margin_left", "text_margin_left"),
            ("margin_bottom", "text_margin_bottom"),
            ("margin_right", "text_margin_right"),
        ]:
            if key in properties and properties[key] is not None:
                try:
                    setattr(tf, attr, Inches(properties[key]))
                except Exception:
                    pass

        if "vertical_alignment" in properties and properties["vertical_alignment"] is not None:
            try:
                anchor_map = {"TOP": "t", "MIDDLE": "ctr", "BOTTOM": "b", "JUSTIFIED": "just", "DISTRIBUTED": "dist"}
                anchor_val = anchor_map.get(properties["vertical_alignment"].upper())
                if anchor_val:
                    bodyPr = tf._txBody.find(qn("a:bodyPr"))
                    if bodyPr is not None:
                        bodyPr.set("anchor", anchor_val)
            except Exception:
                pass
