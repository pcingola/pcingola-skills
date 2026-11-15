"""An animation folder: its files, and the commands init, add-chapter and snapshot."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .animation import Animation
from .chapter import ID_RE, Chapter
from .common import PLAYER, HAError, read_json, write_json
from .enums import ExtraLib, Size, TimingLib
from .lib_pin import PINS
from .vendor import Vendor

# The stub timeline of a new chapter, per timing library. Each returns a paused timeline.
STUBS = {
    TimingLib.GSAP: """HA.chapter("{id}", function (ctx) {{
  var el = ctx.el, content = ctx.content;
  var tl = gsap.timeline({{ paused: true }});
  // tl.from(el("{id}-title"), {{ opacity: 0, y: 40, duration: 0.6, ease: "power2.out" }}, 0.2);
  return tl;
}});
""",
    TimingLib.ANIME: """HA.chapter("{id}", function (ctx) {{
  var el = ctx.el, content = ctx.content;
  var tl = anime.createTimeline({{ autoplay: false }});
  // tl.add(el("{id}-title"), {{ opacity: [0, 1], translateY: [40, 0], duration: 600, ease: "outQuad" }}, 200);
  return tl;
}});
""",
    TimingLib.MOTION: """HA.chapter("{id}", function (ctx) {{
  var el = ctx.el, content = ctx.content;
  var sequence = [
    // [el("{id}-title"), {{ opacity: [0, 1], y: [40, 0] }}, {{ duration: 0.6, ease: "easeOut", at: 0.2 }}],
  ];
  return Motion.animate(sequence);
}});
""",
}

SNAPSHOT_FILES = ("animation.json", "content.json")
VERSION_RE = re.compile(r"^v(\d+)$")


class Project:
    """The animation folder `folder`."""

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder).resolve()

    @property
    def animation_json(self) -> Path:
        return self.folder / "animation.json"

    @property
    def content_json(self) -> Path:
        return self.folder / "content.json"

    @property
    def chapters_dir(self) -> Path:
        return self.folder / "chapters"

    @property
    def lib_dir(self) -> Path:
        return self.folder / "lib"

    @property
    def index_html(self) -> Path:
        return self.folder / "index.html"

    @property
    def player_js(self) -> Path:
        return self.folder / "player.js"

    def chapter_html(self, cid: str) -> Path:
        return self.chapters_dir / f"{cid}.html"

    def chapter_js(self, cid: str) -> Path:
        return self.chapters_dir / f"{cid}.js"

    def exists(self) -> bool:
        return self.animation_json.is_file()

    def load(self) -> Animation:
        return Animation.from_dict(read_json(self.animation_json))

    def save(self, animation: Animation) -> None:
        write_json(self.animation_json, animation.to_dict())

    def content(self) -> dict:
        data = read_json(self.content_json) if self.content_json.is_file() else {}
        if not isinstance(data, dict):
            raise HAError(f"{self.content_json} must be an object")
        return data

    def libs(self) -> list[str]:
        """Keys of the pinned libraries present in lib/, in script order."""
        return [k for k, pin in PINS.items() if (self.lib_dir / pin.file).is_file()]

    def init(self, lib: TimingLib, size: Size = Size.WIDE, title: str | None = None,
             extras: tuple[ExtraLib, ...] = (), vendor: Vendor | None = None) -> dict:
        """Create the folder, or refresh player.js and add libraries in an existing one (its content is kept)."""
        vendor = vendor or Vendor()
        created = not self.exists()
        if created:
            animation = Animation(title=title or self.folder.name, size=size, fps=30, lib=lib)
        else:
            animation = self.load()
            if animation.lib != lib:
                raise HAError(f"{self.folder} uses {animation.lib.value}; init cannot change the timing library")
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.lib_dir.mkdir(exist_ok=True)
        for key in (lib.value, *(e.value for e in extras)):
            pin = PINS[key]
            shutil.copyfile(vendor.path(pin), self.lib_dir / pin.file)
        shutil.copyfile(PLAYER, self.player_js)
        if created:
            self.save(animation)
            write_json(self.content_json, {})
        return {"folder": str(self.folder), "created": created, "lib": lib.value, "libs": self.libs()}

    def add_chapter(self, cid: str, duration: float, title: str | None = None) -> dict:
        """Append a chapter to animation.json and write its empty html and stub script."""
        if not ID_RE.match(cid):
            raise HAError(f"chapter id {cid!r} must match {ID_RE.pattern}")
        if not duration > 0:
            raise HAError("--duration must be above 0")
        animation = self.load()
        if animation.chapter(cid):
            raise HAError(f"chapter {cid!r} exists")
        for path in (self.chapter_html(cid), self.chapter_js(cid)):
            if path.exists():
                raise HAError(f"{path} exists")
        animation.chapters.append(Chapter(cid, title or cid, duration))
        self.chapters_dir.mkdir(exist_ok=True)
        self.chapter_html(cid).write_text("", encoding="utf-8")
        self.chapter_js(cid).write_text(STUBS[animation.lib].format(id=cid), encoding="utf-8")
        self.save(animation)
        return {"chapter": cid, "html": str(self.chapter_html(cid)), "js": str(self.chapter_js(cid)),
                "start": animation.duration - duration, "duration": duration}

    def versions(self) -> list[int]:
        return sorted(int(m.group(1)) for d in self.folder.iterdir() if d.is_dir() and (m := VERSION_RE.match(d.name)))

    def snapshot(self) -> dict:
        """Copy animation.json, content.json and chapters/ into the next v<N>/."""
        if not self.exists():
            raise HAError(f"{self.animation_json} not found")
        n = max(self.versions(), default=0) + 1
        dest = self.folder / f"v{n}"
        dest.mkdir()
        for name in SNAPSHOT_FILES:
            if (self.folder / name).is_file():
                shutil.copy2(self.folder / name, dest / name)
        if self.chapters_dir.is_dir():
            shutil.copytree(self.chapters_dir, dest / "chapters")
        return {"version": n, "dir": str(dest)}
