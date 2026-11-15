"""`python -m html_animation_server <folder> [--port 0] [--parent-pid PID]`: the editor of one animation folder."""

from __future__ import annotations

import argparse
import sys

from .editor import Editor, start_loops
from .handler import serve
from .kinds import LineType


def main() -> None:
    parser = argparse.ArgumentParser(prog="html-animation-server", description=__doc__)
    parser.add_argument("folder", help="the animation folder (relative to the current directory or absolute)")
    parser.add_argument("--port", type=int, default=0, help="port on 127.0.0.1; 0 picks a free one")
    parser.add_argument("--parent-pid", type=int, default=None,
                        help="exit when this process ends (the process that started the wrapper)")
    args = parser.parse_args()
    try:
        editor = Editor(args.folder)
    except ValueError as e:
        sys.exit(f"html-animation server: {e}")
    httpd = serve(editor, args.port)
    editor.emit({"type": LineType.READY.value, "url": editor.url})
    start_loops(editor, parent_pid=args.parent_pid)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
