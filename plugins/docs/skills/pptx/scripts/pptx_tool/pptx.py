#!/usr/bin/env python3
"""Unified CLI for PowerPoint operations on presentations and templates.

`main(argv)` parses the arguments, imports only the module of the command that
runs, calls its `run_<command>(args)` and returns the exit code.

Error output of `PptxError`: `main` prints the exception's `details` lines, then
`Error: <message>`, and returns 1 (`print_error`). The stream is stderr, except for
the commands in `STDOUT_ERROR_COMMANDS`, which print their errors to stdout. A
`run_*` function that prints an error in another format catches the exception itself.
"""
import argparse
import importlib
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from plugin_settings import exit_code

from .exceptions import PptxError

@dataclass(frozen=True)
class CommandRef:
    """Where a command's `run_*` function lives: module in pptx_tool and function name."""
    module: str
    function: str


# Command name -> its run function.
COMMANDS: dict[str, CommandRef] = {
    'select-slides': CommandRef('cmd_select_slides', 'run_select_slides'),
    'inspect-template': CommandRef('cmd_inspect_template', 'run_inspect_template'),
    'inspect-master': CommandRef('cmd_inspect_master', 'run_inspect_master'),
    'extract-text': CommandRef('cmd_check_text', 'run_extract_text'),
    'extract-shapes': CommandRef('cmd_extract_shapes', 'run_extract_shapes'),
    'add-text': CommandRef('cmd_add_text', 'run_add_text'),
    'add-table': CommandRef('cmd_add_table', 'run_add_table'),
    'add-shapes': CommandRef('cmd_add_shapes', 'run_add_shapes'),
    'add-chart': CommandRef('cmd_add_chart', 'run_add_chart'),
    'add-images': CommandRef('cmd_add_images', 'run_add_images'),
    'add-notes': CommandRef('cmd_add_notes', 'run_add_notes'),
    'new-deck': CommandRef('cmd_new_deck', 'run_new_deck'),
    'edit': CommandRef('cmd_edit', 'run_edit'),
    'export-slides': CommandRef('cmd_export_slides', 'run_export_slides'),
    'visual-preview': CommandRef('cmd_visual_preview', 'run_visual_preview'),
    'get': CommandRef('cmd_get', 'run_get'),
    'delete-slide': CommandRef('cmd_delete_slide', 'run_delete_slide'),
    'copy-slide': CommandRef('cmd_copy_slide', 'run_copy_slide'),
    'add-slide': CommandRef('cmd_add_slide', 'run_add_slide'),
    'show-shapes': CommandRef('cmd_show_shapes', 'run_show_shapes'),
    'validate': CommandRef('cmd_validate', 'run_validate'),
    'list-images': CommandRef('cmd_extract_media', 'run_list_images'),
    'extract-images': CommandRef('cmd_extract_media', 'run_extract_images'),
}

# Commands that print their error messages to stdout; all others print them to stderr.
STDOUT_ERROR_COMMANDS = frozenset({
    'add-notes', 'add-shapes', 'add-slide', 'add-table', 'add-text', 'copy-slide',
    'delete-slide', 'extract-shapes', 'get', 'new-deck',
})


def print_error(command: str, exc: PptxError) -> None:
    """Print a PptxError of `command` as the CLI does: its details, then `Error: <message>`."""
    stream = sys.stdout if command in STDOUT_ERROR_COMMANDS else sys.stderr
    for line in exc.details:
        print(line, file=stream)
    print(f'Error: {exc}', file=stream)


def print_unexpected_error(exc: Exception) -> int:
    """Print `Unexpected error: <exc>` to stdout and the traceback to stderr; return exit code 1.

    The output of the write commands that load a data JSON for an exception that is not a PptxError.
    """
    print(f'Unexpected error: {exc}')
    traceback.print_exception(exc)
    return 1


def print_unexpected_failure(exc: Exception) -> bool:
    """Print an exception other than PptxError with `print_unexpected_error` and return True;
    return False for a PptxError, which the caller prints in the standard format.

    The failure output of `add-table` and `add-notes`, as a command and as an `edit` operation.
    """
    if isinstance(exc, PptxError):
        return False
    print_unexpected_error(exc)
    return True


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of every command."""
    parser = argparse.ArgumentParser(prog='pptx', description="PowerPoint CLI for presentations and templates")
    subs = parser.add_subparsers(dest='command', required=True)

    # --- select-slides ---
    p = subs.add_parser('select-slides', help='Select and reorder slides from a template')
    p.add_argument('template', help='Path to template PPTX file')
    p.add_argument('output', help='Path for output PPTX file')
    p.add_argument('sequence', help='Comma-separated sequence of slide indices (0-based)')

    # --- inspect-template ---
    p = subs.add_parser('inspect-template', help='Generate unified template JSON with layout info')
    p.add_argument('template', help='Path to template PPTX file')
    p.add_argument('output', help='Path for output JSON file')

    # --- inspect-master ---
    p = subs.add_parser('inspect-master', help='Inspect slide master and layouts for spurious shapes, confidentiality tags, and template artifacts')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('output', help='Output JSON file')

    # --- extract-text ---
    p = subs.add_parser('extract-text', help='Dump all text as one paragraph per line — no formatting noise')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('-o', '--output', default=None, help='Output file (default: stdout)')
    p.add_argument('--slide', type=int, default=None, help='Single slide by 0-based index (default: all slides)')
    p.add_argument('--json', action='store_true', help='Output as JSON array instead of plain text')

    # --- extract-shapes ---
    p = subs.add_parser('extract-shapes', help='Extract text content and shape data to JSON')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('output', help='Output JSON file, or a directory path (ending with /) to write one slide_N.shapes.json per slide')
    p.add_argument('--issues-only', action='store_true', help='Only include shapes with detected issues')
    p.add_argument('--slide', type=int, default=None, help='Extract a single slide by 0-based index (default: all slides)')

    # --- add-text ---
    p = subs.add_parser('add-text', help='Add text to shapes with automatic overflow prevention')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('text_data', help='Replacement text JSON file')
    p.add_argument('output', help='Output PPTX file')

    # --- new-deck ---
    p = subs.add_parser('new-deck', help='Create a blank deck to draw on (plain white, Calibri)')
    p.add_argument('output', help='Output PPTX file')
    p.add_argument('--slides', type=int, default=1, help='Number of blank slides (default: 1, min: 1)')
    p.add_argument('--size', default='16:9', help='Aspect ratio: 16:9 or 4:3 (default: 16:9)')

    # --- add-shapes ---
    p = subs.add_parser('add-shapes', help='Draw native shapes and pictures at explicit inch coordinates')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('shape_data', help='Shape data JSON file')
    p.add_argument('output', help='Output PPTX file')

    # --- add-notes ---
    p = subs.add_parser('add-notes', help='Set speaker notes text on one or more slides')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('notes_data', help='Notes data JSON file')
    p.add_argument('output', help='Output PPTX file')

    # --- add-table ---
    p = subs.add_parser('add-table', help='Add tables to slides')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('table_data', help='Table data JSON file')
    p.add_argument('output', help='Output PPTX file')

    # --- add-chart ---
    p = subs.add_parser('add-chart', help='Insert a native, editable chart into an OBJECT placeholder')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('output', help='Output PPTX file')
    p.add_argument('slide', type=int, help='Slide index (0-based)')
    p.add_argument('chart_data', help='Chart data JSON file')
    p.add_argument('--index', type=int, default=0,
                   help='OBJECT placeholder index on that slide (default: 0)')

    # --- add-images ---
    p = subs.add_parser('add-images', help='Insert images into placeholders')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('output', help='Output PPTX file')
    p.add_argument('slide', type=int, help='Slide index (0-based)')
    p.add_argument('images', help='Image path or comma-separated paths')
    p.add_argument('--type', dest='placeholder_type', default='PICTURE',
                   help='Placeholder type: PICTURE, OBJECT, MEDIA (default: PICTURE)')
    p.add_argument('--index', type=int, default=None,
                   help='Placeholder index for single image (default: 0)')

    # --- edit ---
    p = subs.add_parser('edit', help='Apply a sequence of operations to a deck in one atomic call')
    p.add_argument('input', help='Input PPTX file (must exist)')
    p.add_argument('output', help='Output PPTX file')
    p.add_argument('spec', help='JSON spec: a path, @path, or an inline JSON string. '
                                '{"operations": [{"action": "<command name>", ...}, ...]}. '
                                'Actions: add-text, add-table, add-notes, add-chart, '
                                'add-images, add-slide, copy-slide, delete-slide')

    # --- export-slides ---
    p = subs.add_parser('export-slides', help='Export each slide as an individual image file')
    p.add_argument('input', type=Path, help='Input PowerPoint file path')
    p.add_argument('output', type=Path, help='Output directory')
    p.add_argument('--dpi', type=int, default=150, help='Resolution in DPI (default: 150)')
    p.add_argument('--format', choices=['jpg', 'png'], default='png', help='Image format (default: png)')

    # --- visual-preview ---
    p = subs.add_parser('visual-preview', help='Generate thumbnail grid JPEGs')
    p.add_argument('input', type=Path, help='Input PowerPoint file path')
    p.add_argument('output', type=Path, nargs='?', help='Output file prefix (optional)')
    p.add_argument('--cols', type=int, default=5, help='Number of columns (default: 5, range: 3-6)')
    p.add_argument('--outline-text', action='store_true', help='Draw red outlines around text placeholders')

    # --- get ---
    p = subs.add_parser('get', help='Read a single shape\'s text content, or a slide\'s speaker notes')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('shape_path', help='Shape path (e.g. slide-0/shape-2) or slide-N/notes for speaker notes')

    # --- delete-slide ---
    p = subs.add_parser('delete-slide', help='Remove slides from a presentation by index')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('output', help='Output PPTX file')
    p.add_argument('indices', help='Comma-separated slide indices to delete (0-based)')

    # --- add-slide ---
    p = subs.add_parser('add-slide', help='Add new slides from the deck\'s own layouts, by layout name')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('output', help='Output PPTX file')
    p.add_argument('layouts', help='Comma-separated layout names, one new slide each, in order')
    p.add_argument('--position', type=int, default=None, help='Insert position (0-based, default: end)')

    # --- copy-slide ---
    p = subs.add_parser('copy-slide', help='Copy slides from source into target presentation')
    p.add_argument('source', help='Source PPTX file')
    p.add_argument('target', help='Target PPTX file')
    p.add_argument('output', help='Output PPTX file')
    p.add_argument('source_indices', help='Comma-separated source slide indices')
    p.add_argument('--position', type=int, default=None, help='Insert position in target (default: end)')

    # --- show-shapes ---
    p = subs.add_parser('show-shapes', help='Summarize extracted shapes JSON (from extract-shapes) in compact form')
    p.add_argument('input', help='Extracted shapes JSON file (output of extract-shapes)')

    # --- list-images ---
    p = subs.add_parser('list-images', help='List embedded images per slide')
    p.add_argument('input', help='Input PPTX file')

    # --- extract-images ---
    p = subs.add_parser('extract-images', help='Extract embedded images to a directory')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('-o', '--output', required=True, help='Output directory')
    p.add_argument('--min-bytes', type=int, default=2048,
                   help='Skip images smaller than this many bytes (default: 2048)')
    p.add_argument('--min-pixels', default='50x50',
                   help='Skip images below WxH pixels (default: 50x50)')

    # --- validate ---
    p = subs.add_parser('validate', help='Check a deck for overflow, empty placeholders, and unfilled visual slots')
    p.add_argument('input', help='Input PPTX file')
    p.add_argument('output', nargs='?', help='Output JSON path (default: stdout)')

    return parser


def _command(name: str) -> Callable[[argparse.Namespace], int | None]:
    """Import the module of one command and return its `run_*` function."""
    ref = COMMANDS[name]
    module = importlib.import_module(f'.{ref.module}', __package__)
    return getattr(module, ref.function)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI on `argv` (default: `sys.argv[1:]`) and return the exit code.

    argparse exits with 0 for `--help` and 2 for an argument error; `main` returns
    that code. A `run_*` function returns its exit code (None means 0). `PptxError`
    is printed as `Error: <message>` (stream: see the module docstring) and gives 1.
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exit_code(exc)
    try:
        return _command(args.command)(args) or 0
    except PptxError as exc:
        print_error(args.command, exc)
        return 1
