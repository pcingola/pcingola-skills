"""Set speaker notes text on one or more slides.

The notes data JSON uses slide-N keys, each mapping to a plain-text string. Use
"\\n" within the string to split the notes into separate paragraphs. Setting
notes never touches slide content (shapes, text, images) -- only the slide's
notes page. Works on both blank-canvas decks and template-based decks.
"""

from pathlib import Path

from pptx import Presentation

from .common import load_data_json, require_file
from .exceptions import PptxError, ValidationError
from .pptx import print_unexpected_error


class PresentationNotesSetter:
    """Sets speaker notes text on slides from a JSON definition."""

    def add_notes(self, input_path: Path, notes_data: dict, output_path: Path) -> list[str]:
        """Set the notes of each slide-N key of `notes_data` and save the deck to output_path.

        Returns the slide keys set, in slide order. Invalid data raises ValidationError with one
        detail line per problem.
        """
        require_file(input_path, f"Input file '{input_path}' not found")
        prs = Presentation(str(input_path))
        self._validate_notes_data(prs, notes_data)

        for slide_key, text in notes_data.items():
            slide_index = int(slide_key.split("-")[1])
            slide = prs.slides[slide_index]
            self._set_notes(slide, text)

        prs.save(str(output_path))
        return sorted(notes_data, key=lambda k: int(k.split("-")[1]))

    def _validate_notes_data(self, prs, notes_data: dict) -> None:
        errors = []
        slide_count = len(prs.slides)

        for slide_key, text in notes_data.items():
            if not slide_key.startswith("slide-"):
                errors.append(f"Invalid key '{slide_key}': must be 'slide-N'")
                continue
            try:
                slide_index = int(slide_key.split("-")[1])
            except (IndexError, ValueError):
                errors.append(f"Invalid slide key '{slide_key}'")
                continue
            if slide_index < 0 or slide_index >= slide_count:
                errors.append(f"Slide index {slide_index} out of range (0-{slide_count - 1})")
                continue
            if not isinstance(text, str):
                errors.append(
                    f"{slide_key}: notes value must be a string, got {type(text).__name__}"
                )

        if errors:
            raise ValidationError(
                f"Found {len(errors)} validation error(s)",
                ["ERROR: Invalid notes data:", *(f"  - {error}" for error in errors)],
            )

    def _set_notes(self, slide, text: str) -> None:
        tf = slide.notes_slide.notes_text_frame
        tf.clear()
        # tf.clear() preserves the retained first paragraph's <a:pPr> (alignment,
        # indent, bullet) -- drop it too so stale formatting from a previous
        # add-notes call, or from manual PowerPoint edits, doesn't carry over.
        first_para_pPr = tf.paragraphs[0]._p.pPr
        if first_para_pPr is not None:
            tf.paragraphs[0]._p.remove(first_para_pPr)

        lines = text.split("\n")
        for i, line in enumerate(lines):
            paragraph = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            paragraph.text = line


def run_add_notes(args) -> int:
    """Entry point from CLI dispatcher."""
    input_pptx = Path(args.input)
    output_pptx = Path(args.output)
    # The CLI reports a missing input before a missing or malformed notes data file.
    require_file(input_pptx, f"Input file '{input_pptx}' not found")
    try:
        notes_data = load_data_json(Path(args.notes_data), "Notes data")
        slide_keys = PresentationNotesSetter().add_notes(input_pptx, notes_data, output_pptx)
    except PptxError:
        raise
    except Exception as e:
        return print_unexpected_error(e)
    print(f"Saved presentation to: {output_pptx}")
    for slide_key in slide_keys:
        print(f"  {slide_key}: notes set")
    return 0
