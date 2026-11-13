"""Set speaker notes text on one or more slides.

The notes data JSON uses slide-N keys, each mapping to a plain-text string. Use
"\\n" within the string to split the notes into separate paragraphs. Setting
notes never touches slide content (shapes, text, images) -- only the slide's
notes page. Works on both blank-canvas decks and template-based decks.
"""

import json
import sys
from pathlib import Path

from pptx import Presentation

from .exceptions import ValidationError


class PresentationNotesSetter:
    """Sets speaker notes text on slides from a JSON definition."""

    def add_notes(self, input_path: str, notes_data_path: str, output_path: str) -> None:
        prs = Presentation(input_path)
        notes_data = self._load_notes_data(notes_data_path)
        self._validate_notes_data(prs, notes_data)

        for slide_key, text in notes_data.items():
            slide_index = int(slide_key.split("-")[1])
            slide = prs.slides[slide_index]
            self._set_notes(slide, text)

        prs.save(output_path)
        print(f"Saved presentation to: {output_path}")
        for slide_key in sorted(notes_data, key=lambda k: int(k.split("-")[1])):
            print(f"  {slide_key}: notes set")

    def _load_notes_data(self, json_path: str) -> dict:
        with open(json_path, "r") as f:
            return json.load(f, object_pairs_hook=self._check_duplicate_keys)

    @staticmethod
    def _check_duplicate_keys(pairs: list[tuple]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(f"Duplicate key found in JSON: '{key}'")
            result[key] = value
        return result

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
            print("ERROR: Invalid notes data:")
            for error in errors:
                print(f"  - {error}")
            raise ValidationError(f"Found {len(errors)} validation error(s)")

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


def run_add_notes(args) -> None:
    """Entry point from CLI dispatcher."""
    input_pptx = Path(args.input)
    notes_data_json = Path(args.notes_data)
    output_pptx = Path(args.output)

    if not input_pptx.exists():
        print(f"Error: Input file '{input_pptx}' not found")
        sys.exit(1)

    if not notes_data_json.exists():
        print(f"Error: Notes data JSON file '{notes_data_json}' not found")
        sys.exit(1)

    try:
        setter = PresentationNotesSetter()
        setter.add_notes(str(input_pptx), str(notes_data_json), str(output_pptx))
    except ValidationError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
