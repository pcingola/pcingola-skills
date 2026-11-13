"""Write a self-contained deck directory and check the files a deck references."""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

SKILL_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = SKILL_DIR / "assets"
VENDOR_DIR = ASSETS_DIR / "reveal.js"
TEMPLATE = ASSETS_DIR / "template.html"
VENDOR_NAME = "reveal.js"  # directory name of the copy inside a deck

# Attributes whose value is a file the page loads, per tag ("*" = any tag).
_LOADED = {
    "script": ("src",),
    "link": ("href",),
    "img": ("src",),
    "source": ("src",),
    "video": ("src", "poster"),
    "audio": ("src",),
    "iframe": ("src",),
    "*": (
        "data-background", "data-background-image", "data-background-video", "data-background-iframe",
        "data-markdown",  # external Markdown file; an empty value means inline Markdown
    ),
}
# `<link rel>` tokens whose href the page loads
_LINK_LOADED_RELS = {"stylesheet", "icon", "preload", "modulepreload"}
# reveal.js config `katex: { ... local: '<dir>' ... }`; the math plugin appends _KATEX_FILES.
_KATEX_KEY = re.compile(r"""(?<![\w$.])['"]?katex['"]?\s*:\s*\{""")
_KATEX_LOCAL = re.compile(r"""\blocal\s*:\s*['"]([^'"]+)['"]""")
# Markdown image `![alt](path "title")` and HTML `<img src="path">` inside Markdown
_MD_IMAGE = re.compile(r"""!\[[^\]]*\]\(\s*<?([^)\s>]+)""")
_MD_IMG_TAG = re.compile(r"""<img\b[^>]*\bsrc\s*=\s*['"]([^'"]+)['"]""", re.IGNORECASE)
_KATEX_FILES = ("dist/katex.min.css", "dist/katex.min.js", "dist/contrib/auto-render.min.js")
_CSS_REMOTE_IMPORT = re.compile(r"""@import\s+url\(\s*['"]?(https?://[^'")]+)""")


def themes() -> list[str]:
    """Theme names available in the vendored copy."""
    return sorted(p.stem for p in (VENDOR_DIR / "dist" / "theme").glob("*.css"))


def new_deck(dest: Path, title: str = "Presentation", theme: str = "black", force: bool = False) -> Path:
    """Create `dest/index.html` from the template and copy reveal.js to `dest/reveal.js/`.

    Returns the path of the written HTML file.
    """
    if theme not in themes():
        raise ValueError(f"unknown theme {theme!r}; available: {', '.join(themes())}")
    dest = Path(dest)
    index = dest / "index.html"
    if index.exists() and not force:
        raise FileExistsError(f"{index} exists (use --force to overwrite)")
    dest.mkdir(parents=True, exist_ok=True)
    copy_vendor(dest)
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace("{{title}}", html.escape(title)).replace("{{theme}}", theme)
    index.write_text(text, encoding="utf-8")
    return index


def copy_vendor(dest: Path) -> Path:
    """Copy (or refresh) the vendored reveal.js into `dest/reveal.js/`."""
    vendor = Path(dest) / VENDOR_NAME
    if vendor.exists():
        shutil.rmtree(vendor)
    shutil.copytree(VENDOR_DIR, vendor)
    return vendor


@dataclass(frozen=True)
class Ref:
    tag: str
    attr: str
    value: str


class _RefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[Ref] = []
        self.scripts: list[str] = []
        self._in_script = False
        self._in_template = False

    def handle_starttag(self, tag, attrs):
        wanted = _LOADED.get(tag, ()) + _LOADED["*"]
        for name, value in attrs:
            if name not in wanted or not value:
                continue
            if tag == "link" and name == "href":
                rels = set((dict(attrs).get("rel") or "").lower().split())
                if not rels & _LINK_LOADED_RELS:
                    continue
            # data-background-video takes a comma-separated list of sources
            parts = value.split(",") if name == "data-background-video" else [value]
            for part in parts:
                self.refs.append(Ref(tag, name, part.strip()))
        self._in_script = tag == "script"
        if tag == "textarea" and any(name == "data-template" for name, _ in attrs):
            self._in_template = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False
        elif tag == "textarea":
            self._in_template = False

    def handle_data(self, data):
        if self._in_script:
            self.scripts.append(data)
        elif self._in_template:
            self.refs.extend(markdown_refs(data, "inline markdown"))


def markdown_refs(text: str, where: str) -> list[Ref]:
    """Image references in Markdown text (Markdown syntax and `<img src>`)."""
    found = _MD_IMAGE.findall(text) + _MD_IMG_TAG.findall(text)
    return [Ref(where, "image", value) for value in found]


def collect_refs(text: str) -> tuple[list[Ref], list[str]]:
    """Return the file references in an HTML page and its inline script bodies.

    Includes images inside inline Markdown slides (`<textarea data-template>`).
    """
    parser = _RefParser()
    parser.feed(text)
    parser.close()
    return parser.refs, parser.scripts


def _is_remote(value: str) -> bool:
    return urlsplit(value).scheme in ("http", "https") or value.startswith("//")


def _is_local_file(value: str) -> bool:
    parts = urlsplit(value)
    if parts.scheme or value.startswith(("#", "//")):
        return False
    # data-background may be a colour or gradient, not a file
    if value.startswith(("rgb", "hsl", "linear-gradient", "radial-gradient")):
        return False
    return bool(parts.path)


def _is_color(value: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-zA-Z]+", value)) and "." not in value


def _object_end(text: str, start: int) -> int:
    """Index just past the `}` matching the `{` at `text[start]`, skipping string literals.

    Returns len(text) if the object is not closed.
    """
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c in "'\"`":
            i += 1
            while i < len(text) and text[i] != c:
                i += 2 if text[i] == "\\" else 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def katex_configs(script: str) -> list[str]:
    """The `{...}` bodies of every `katex: {...}` object in a script, nested braces included."""
    return [script[m.end() - 1:_object_end(script, m.end() - 1)] for m in _KATEX_KEY.finditer(script)]


@dataclass(frozen=True)
class Problem:
    level: str  # "error" or "warning"
    message: str


def check_deck(html_path: Path) -> list[Problem]:
    """Check that every file `html_path` loads exists locally.

    Errors: a missing local file (including external Markdown files and the
    images inside Markdown slides), a remote script or stylesheet (breaks
    offline), a KaTeX `local` directory without KaTeX in it. Warnings: other
    remote media, external Markdown (needs an HTTP server, not file://), and
    stylesheets that @import from the network (themes using Google Fonts).
    """
    html_path = Path(html_path)
    base = html_path.parent
    refs, scripts = collect_refs(html_path.read_text(encoding="utf-8"))
    problems: list[Problem] = []
    while refs:
        ref = refs.pop(0)
        where = f"<{ref.tag} {ref.attr}={ref.value!r}>"
        if _is_remote(ref.value):
            if ref.tag in ("script", "link"):
                problems.append(Problem("error", f"remote {where}: deck will not work offline"))
            else:
                problems.append(Problem("warning", f"remote {where}"))
            continue
        if ref.attr == "data-background" and _is_color(ref.value):
            continue
        if not _is_local_file(ref.value):
            continue
        target = base / unquote(urlsplit(ref.value).path)
        if not target.is_file():
            problems.append(Problem("error", f"missing {where}: {target}"))
            continue
        if ref.attr == "data-markdown":
            problems.append(Problem(
                "warning",
                f"{where}: external Markdown is fetched by XHR, which browsers block from file://; "
                "serve the deck directory over HTTP (python3 -m http.server) or inline it in <textarea data-template>",
            ))
            # images in the Markdown resolve against the deck HTML, where the slides end up
            refs.extend(markdown_refs(target.read_text(encoding="utf-8", errors="replace"), ref.value))
        if target.suffix == ".css":
            for url in _CSS_REMOTE_IMPORT.findall(target.read_text(encoding="utf-8", errors="replace")):
                problems.append(
                    Problem("warning", f"{ref.value} imports {url}; offline the browser falls back to system fonts")
                )
    script_text = "\n".join(scripts)
    if "RevealMath.MathJax" in script_text:
        problems.append(Problem("error", "MathJax is not vendored and loads from a CDN; use RevealMath.KaTeX"))
    if "RevealMath" in script_text:
        locals_ = [local for config in katex_configs(script_text) for local in _KATEX_LOCAL.findall(config)]
        if "RevealMath.KaTeX" in script_text and not locals_:
            problems.append(
                Problem("error", "RevealMath.KaTeX without `katex: { local: ... }` loads KaTeX from a CDN")
            )
        for local in locals_:
            for rel in _KATEX_FILES:
                target = base / local / rel
                if not target.is_file():
                    problems.append(Problem("error", f"missing KaTeX file {target} (katex.local={local!r})"))
    return problems
