"""animation.json: title, size, stage pixels, fps, timing library and the chapters in order."""
from __future__ import annotations

from dataclasses import dataclass, field

from .chapter import ID_RE, Chapter
from .common import HAError
from .enums import Size, TimingLib

KEYS = {"title", "size", "width", "height", "fps", "lib", "chapters"}


@dataclass
class Animation:
    title: str
    size: Size
    fps: int
    lib: TimingLib
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def width(self) -> int:
        return self.size.pixels[0]

    @property
    def height(self) -> int:
        return self.size.pixels[1]

    @property
    def duration(self) -> float:
        return sum(c.duration for c in self.chapters)

    def chapter(self, cid: str) -> Chapter | None:
        return next((c for c in self.chapters if c.id == cid), None)

    def to_dict(self) -> dict:
        return {"title": self.title, "size": self.size.value, "width": self.width, "height": self.height,
                "fps": self.fps, "lib": self.lib.value, "chapters": [c.to_dict() for c in self.chapters]}

    @staticmethod
    def problems(data: object) -> list[str]:
        """What makes `data` an invalid animation.json; [] when it is valid."""
        if not isinstance(data, dict):
            return ["animation.json must be an object"]
        out = [f"unknown key {k!r}" for k in sorted(set(data) - KEYS)]
        out += [f"missing key {k!r}" for k in sorted(KEYS - set(data))]
        title = data.get("title")
        if "title" in data and (not isinstance(title, str) or not title.strip()):
            out.append("title must be a non-empty string")
        size = data.get("size")
        sizes = [s.value for s in Size]
        if "size" in data and size not in sizes:
            out.append(f"size must be one of {', '.join(sizes)}")
        elif size in sizes:
            w, h = Size(size).pixels
            if data.get("width") != w or data.get("height") != h:
                out.append(f"width and height must be {w} and {h} for size {size}")
        fps = data.get("fps")
        if "fps" in data and (not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 120):
            out.append("fps must be an integer from 1 to 120")
        libs = [lib.value for lib in TimingLib]
        if "lib" in data and data.get("lib") not in libs:
            out.append(f"lib must be one of {', '.join(libs)}")
        chapters = data.get("chapters")
        if "chapters" in data and not isinstance(chapters, list):
            out.append("chapters must be a list")
        elif isinstance(chapters, list):
            seen: set[str] = set()
            for i, c in enumerate(chapters):
                where = f"chapters[{i}]"
                if not isinstance(c, dict):
                    out.append(f"{where} must be an object")
                    continue
                out += [f"{where}: unknown key {k!r}" for k in sorted(set(c) - {"id", "title", "duration"})]
                cid = c.get("id")
                if not isinstance(cid, str) or not ID_RE.match(cid):
                    out.append(f"{where}: id must match {ID_RE.pattern}")
                elif cid in seen:
                    out.append(f"{where}: duplicate id {cid!r}")
                else:
                    seen.add(cid)
                if not isinstance(c.get("title", ""), str):
                    out.append(f"{where}: title must be a string")
                d = c.get("duration")
                if isinstance(d, bool) or not isinstance(d, (int, float)) or not 0 < d <= 3600:
                    out.append(f"{where}: duration must be a number of seconds, above 0 and at most 3600")
        return out

    @classmethod
    def from_dict(cls, data: object) -> Animation:
        """The animation of a valid animation.json; HAError listing every problem otherwise."""
        bad = cls.problems(data)
        if bad:
            raise HAError("animation.json: " + "; ".join(bad))
        assert isinstance(data, dict)
        return cls(title=data["title"], size=Size(data["size"]), fps=data["fps"], lib=TimingLib(data["lib"]),
                   chapters=[Chapter(c["id"], c.get("title", c["id"]), c["duration"]) for c in data["chapters"]])
