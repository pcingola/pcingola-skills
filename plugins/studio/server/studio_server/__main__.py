"""`python -m studio_server [--parent-pid PID]`: serve the projects root `STUDIO_DIR` (default ~/Documents/Studio)."""

from __future__ import annotations

import argparse
import os

from plugin_settings import Plugin

from .catalogue import find_brand_plugin
from .server import Studio, start_loops

DEFAULT_ROOT = "~/Documents/Studio"


def projects_root() -> str:
    """`STUDIO_DIR` from the settings, else DEFAULT_ROOT; `~` is expanded by the server. A relative path
    exits with an error naming where it was set."""
    plugin = Plugin.of(__file__)
    plugin.load()
    value = (plugin.get("STUDIO_DIR") or "").strip() or DEFAULT_ROOT
    if not os.path.isabs(os.path.expanduser(value)):
        plugin.invalid("STUDIO_DIR", value, "an absolute path or one starting with ~")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(prog="studio-server", description=__doc__)
    parser.add_argument("--parent-pid", type=int, default=None,
                        help="exit when this process ends (the process that started the wrapper)")
    args = parser.parse_args()
    studio_root = Plugin.of(__file__).root
    studio = Studio(projects_root(), find_brand=lambda: find_brand_plugin(studio_root) if studio_root else None)
    httpd = studio.serve()
    studio.emit({"type": "ready", "url": studio.url})
    studio.start_catalogue()
    start_loops(studio, parent_pid=args.parent_pid)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
