"""The `/scene/` route: the files of a short-video scene or world version, for the scene player's iframe.

`/scene/<token>/<directory>/<project>/(scenes|worlds)/<name>/v<N>/<file>` serves one file of that version directory
of a short-video project, so the page's relative URLs (`gsap.min.js`, `timing.js`, `background.png`) resolve. No
component may be a symbolic link, hidden or `..`. `index.html` is served with the page's `scene-player.js` inlined
before `</body>`; the file on disk is not changed. `<token>` is random per server run (video.SCENE_PREFIX) and reaches
the page only in `page_url` of /api/project; a path under `/scene/` with another token is answered 404.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from .paths import HttpError, inside
from .video import DIRECTORY, SCENE_ID, SCENE_PREFIX, VERSION_DIR

PREFIX = SCENE_PREFIX
# Every path under it, any token.
ROUTE = "/scene/"
TOPS = ("scenes", "worlds")
PAGE = "index.html"
PLAYER = "scene-player.js"


def scene_file(root: Path, raw: str) -> Path:
    """The file a `/scene/<token>/` URL path (still percent-encoded) names; 403 for a path outside a version directory of a
    short-video project, 404 for a missing file."""
    parts = [unquote(p) for p in raw[len(PREFIX):].split("/")]
    bad = [p for p in parts if not p or p.startswith(".") or any(c in p for c in "/\\\0")]
    if bad or len(parts) < 6:
        raise HttpError(403, "not a file of a scene version")
    directory, project, top, name, version, *rest = parts
    if directory != DIRECTORY or top not in TOPS or not SCENE_ID.match(name) or not VERSION_DIR.match(version):
        raise HttpError(403, "not a file of a scene version")
    path = root
    for part in (directory, project, top, name, version, *rest):
        path = path / part
        if path.is_symlink():
            raise HttpError(403, "a symbolic link is not served")
    if not inside(path.resolve(), root) or not path.is_file():
        raise HttpError(404, f"no file {'/'.join(parts)}")
    return path


def with_player(html: bytes, script: bytes) -> bytes:
    """`html` with `script` inlined in a `<script>` element before the last `</body>`, or at the end without one."""
    tag = b"<script>\n" + script.replace(b"</script", b"<\\/script") + b"\n</script>\n"
    k = html.lower().rfind(b"</body>")
    return html + tag if k < 0 else html[:k] + tag + html[k:]
