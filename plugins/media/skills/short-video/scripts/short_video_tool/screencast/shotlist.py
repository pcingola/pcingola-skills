"""Reading and checking a YAML shot list (format: the skill's `references/screencast.md`).

Every key is checked: an unknown key, a missing file or a value of the wrong shape is an error naming its
place (`shots[2].camera[0].zoom`). Relative paths resolve against the shot list's directory. Colours are
`#RRGGBB` or a name of the style's `palette`; a colour left out takes the palette's `accent` (highlights,
clicks, labels), `mark` (drawn marks) or `divider` (wipes).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .. import settings
from .model import (Anchor, CameraSpec, Card, CardPose, Click, Draw, Grade, Highlight, Insert, Label, LabelEdge, Patch,
                    Shape, Shot, ShotKind, ShotList, Typing, Wipe)
from .style import Style, StyleError

TOP_KEYS = {"style", "fade", "shots"}
SHOT_KEYS = {"type", "length", "fade", "video", "from", "to", "times", "image", "wipe", "scale", "upscale", "rect",
             "radius", "camera", "highlights", "clicks", "labels", "caption", "draw", "patches", "typing", "inserts",
             "cards", "glow", "grade", "note"}
# Keys each kind of shot takes beyond the common ones.
COMMON = {"type", "length", "fade", "labels", "caption", "note"}
KIND_KEYS = {
    ShotKind.PANEL: COMMON | {"video", "from", "to", "times", "image", "wipe", "scale", "upscale", "rect", "radius",
                              "camera", "highlights", "clicks", "draw", "patches", "typing", "inserts", "grade"},
    ShotKind.PICTURE: COMMON | {"image", "wipe", "scale", "upscale", "camera", "highlights", "clicks", "draw",
                                "patches", "grade"},
    ShotKind.CARDS: COMMON | {"cards", "glow"},
}


class ScreencastError(ValueError):
    pass


class Parser:
    def __init__(self, base: Path, style: Style):
        self.base, self.style = base, style

    # ---- scalars ----
    @staticmethod
    def keys(d: object, allowed: set[str], where: str, required: tuple[str, ...] = ()) -> dict:
        if not isinstance(d, dict):
            raise ScreencastError(f"{where}: expected a mapping, got {d!r}")
        unknown = sorted(set(d) - allowed)
        if unknown:
            raise ScreencastError(f"{where}: unknown key {unknown[0]!r} (allowed: {', '.join(sorted(allowed))})")
        for k in required:
            if k not in d:
                raise ScreencastError(f"{where}: `{k}` is required")
        return d

    @staticmethod
    def num(v: object, where: str, positive: bool = False) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ScreencastError(f"{where}: expected a number, got {v!r}")
        if positive and v <= 0:
            raise ScreencastError(f"{where}: must be above 0")
        return float(v)

    def nums(self, v: object, n: int, where: str) -> tuple[float, ...]:
        if not isinstance(v, (list, tuple)) or len(v) != n:
            raise ScreencastError(f"{where}: expected a list of {n} numbers, got {v!r}")
        return tuple(self.num(x, f"{where}[{i}]") for i, x in enumerate(v))

    def rect(self, v: object, where: str):
        r = self.nums(v, 4, where)
        if r[2] <= 0 or r[3] <= 0:
            raise ScreencastError(f"{where}: width and height must be above 0")
        return r

    def path(self, v: object, where: str, video: bool = False) -> Path:
        if not isinstance(v, str) or not v:
            raise ScreencastError(f"{where}: expected a file path")
        p = Path(v).expanduser()
        p = p if p.is_absolute() else self.base / p
        if not p.is_file():
            raise ScreencastError(f"{where}: {p} not found")
        return p

    def color(self, v: object, default: str, where: str):
        try:
            return self.style.color(v, default)
        except StyleError as e:
            raise ScreencastError(f"{where}: {e}") from None

    @staticmethod
    def enum(cls, v: object, where: str):
        try:
            return cls(v)
        except ValueError:
            raise ScreencastError(f"{where}: {v!r} is not one of {', '.join(m.value for m in cls)}") from None

    def items(self, v: object, where: str) -> list:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ScreencastError(f"{where}: expected a list")
        return v

    def span(self, d: dict, where: str, length: float, start: str = "from", end: str = "to") -> tuple[float, float]:
        a = self.num(d.get(start, 0.0), f"{where}.{start}")
        b = self.num(d.get(end, length), f"{where}.{end}")
        if b < a:
            raise ScreencastError(f"{where}: `{end}` is before `{start}`")
        return a, b

    # ---- parts ----
    def camera(self, v: object, where: str) -> list[CameraSpec]:
        out = []
        for i, k in enumerate(self.items(v, where)):
            w = f"{where}[{i}]"
            k = self.keys(k, {"t", "center", "zoom", "width", "rect", "yaw", "pitch"}, w, ("t",))
            out.append(CameraSpec(
                t=self.num(k["t"], f"{w}.t"),
                center=self.nums(k["center"], 2, f"{w}.center") if "center" in k else None,
                zoom=self.num(k["zoom"], f"{w}.zoom", True) if "zoom" in k else None,
                width=self.num(k["width"], f"{w}.width", True) if "width" in k else None,
                rect=self.rect(k["rect"], f"{w}.rect") if "rect" in k else None,
                yaw=self.num(k["yaw"], f"{w}.yaw") if "yaw" in k else None,
                pitch=self.num(k["pitch"], f"{w}.pitch") if "pitch" in k else None))
            if i and out[-1].t < out[-2].t:
                raise ScreencastError(f"{w}.t: camera keys must be in time order")
        return out

    def label(self, d: object, where: str, length: float, caption: bool = False) -> Label:
        if isinstance(d, str):
            d = {"text": d}
        allowed = {"text", "from", "to", "color", "size"} | (set() if caption else {"at", "page", "anchor"})
        d = self.keys(d, allowed, where, ("text",) if caption else ("text", "at"))
        a, b = self.span(d, where, length)
        return Label(
            text=str(d["text"]), start=a, end=b, color=self.color(d.get("color"), "accent", f"{where}.color"),
            at=self.nums(d["at"], 2, f"{where}.at") if "at" in d else None, page=bool(d.get("page", False)),
            anchor=self.enum(Anchor, d.get("anchor", "left"), f"{where}.anchor"),
            size=self.num(d["size"], f"{where}.size", True) if "size" in d else None, caption=caption)

    def wipe(self, d: object, where: str) -> Wipe:
        d = self.keys(d, {"before", "after", "divider", "color", "labels", "label_colors", "label_edge", "fade",
                          "align"}, where, ("before", "after", "divider"))
        div = [self.nums(k, 2, f"{where}.divider[{i}]") for i, k in enumerate(self.items(d["divider"],
                                                                                        f"{where}.divider"))]
        if not div:
            raise ScreencastError(f"{where}.divider: at least one [t, x] key")
        labels = d.get("labels")
        if labels is not None and (not isinstance(labels, list) or len(labels) != 2):
            raise ScreencastError(f"{where}.labels: two texts, [before, after]")
        lc = d.get("label_colors")
        if lc is not None and (not isinstance(lc, list) or len(lc) != 2):
            raise ScreencastError(f"{where}.label_colors: two colours, [before, after]")
        return Wipe(
            before=self.path(d["before"], f"{where}.before"), after=self.path(d["after"], f"{where}.after"),
            divider=div, color=self.color(d.get("color"), "divider", f"{where}.color"),
            labels=(str(labels[0]), str(labels[1])) if labels else None,
            label_colors=tuple(self.color(c, "accent", f"{where}.label_colors") for c in lc) if lc else None,
            label_edge=self.enum(LabelEdge, d.get("label_edge", "top"), f"{where}.label_edge"),
            fade=self.nums(d["fade"], 2, f"{where}.fade") if "fade" in d else None,
            align=bool(d.get("align", True)))

    def shot(self, d: object, where: str, index: int, fade: float) -> Shot:
        d = self.keys(d, SHOT_KEYS, where, ("length",))
        kind = self.enum(ShotKind, d.get("type", "panel"), f"{where}.type")
        extra = sorted(set(d) - KIND_KEYS[kind])
        if extra:
            raise ScreencastError(f"{where}: a {kind.value} shot takes no `{extra[0]}`")
        n = self.num(d["length"], f"{where}.length", True)
        s = Shot(kind=kind, length=n, fade=self.num(d.get("fade", fade), f"{where}.fade"), index=index)
        if kind is ShotKind.CARDS:
            self.cards(s, d, where)
        else:
            self.page(s, d, where, kind)
        s.labels = [self.label(x, f"{where}.labels[{i}]", n) for i, x in enumerate(self.items(d.get("labels"),
                                                                                              f"{where}.labels"))]
        if "caption" in d:
            s.labels.append(self.label(d["caption"], f"{where}.caption", n, caption=True))
        return s

    def cards(self, s: Shot, d: dict, where: str) -> None:
        for i, c in enumerate(self.items(d.get("cards"), f"{where}.cards")):
            w = f"{where}.cards[{i}]"
            c = self.keys(c, {"image", "upscale", "keys"}, w, ("image", "keys"))
            keys = []
            for j, k in enumerate(self.items(c["keys"], f"{w}.keys")):
                kw = f"{w}.keys[{j}]"
                k = self.keys(k, {"t", "center", "width", "angle", "alpha"}, kw, ("t", "center", "width"))
                keys.append(CardPose(self.num(k["t"], f"{kw}.t"), self.nums(k["center"], 2, f"{kw}.center"),
                                     self.num(k["width"], f"{kw}.width"), self.num(k.get("angle", 0.0), f"{kw}.angle"),
                                     self.num(k.get("alpha", 1.0), f"{kw}.alpha")))
            if not keys:
                raise ScreencastError(f"{w}.keys: at least one key")
            s.cards.append(Card(self.path(c["image"], f"{w}.image"), keys,
                                int(c["upscale"]) if c.get("upscale") else None))
        if not s.cards:
            raise ScreencastError(f"{where}.cards: at least one card")
        s.glow = self.color(d["glow"], "accent", f"{where}.glow") if d.get("glow") is not None else None

    def page(self, s: Shot, d: dict, where: str, kind: ShotKind) -> None:
        sources = [k for k in ("video", "image", "wipe") if k in d]
        if len(sources) != 1:
            raise ScreencastError(f"{where}: give exactly one of `video`, `image`, `wipe`")
        n = s.length
        if "video" in d:
            s.video = self.path(d["video"], f"{where}.video")
            if "times" in d:
                if "from" in d or "to" in d:
                    raise ScreencastError(f"{where}: `times` replaces `from` and `to`")
                s.times = [self.nums(x, 2, f"{where}.times[{i}]")
                           for i, x in enumerate(self.items(d["times"], f"{where}.times"))]
                if len(s.times) < 2:
                    raise ScreencastError(f"{where}.times: at least two [shot time, recording time] points")
            else:
                s.start = self.num(d.get("from", 0.0), f"{where}.from")
                s.end = self.num(d["to"], f"{where}.to") if "to" in d else None
        elif any(k in d for k in ("from", "to", "times")):
            raise ScreencastError(f"{where}: `from`, `to` and `times` belong to a `video` shot")
        if "image" in d:
            s.image = self.path(d["image"], f"{where}.image")
        if "wipe" in d:
            s.wipe = self.wipe(d["wipe"], f"{where}.wipe")
        s.scale = self.num(d.get("scale", 1.0), f"{where}.scale", True)
        s.upscale = int(self.num(d["upscale"], f"{where}.upscale", True)) if "upscale" in d else None
        s.rect = self.rect(d["rect"], f"{where}.rect") if "rect" in d else None
        s.radius = self.num(d["radius"], f"{where}.radius") if "radius" in d else None
        s.camera = self.camera(d.get("camera"), f"{where}.camera")
        if "grade" in d:
            g = self.keys(d["grade"], {"gamma", "gain", "tint"}, f"{where}.grade")
            s.grade = Grade(self.num(g.get("gamma", 1.0), f"{where}.grade.gamma", True),
                            self.num(g.get("gain", 1.0), f"{where}.grade.gain", True),
                            self.nums(g.get("tint", [1.0, 1.0, 1.0]), 3, f"{where}.grade.tint"))
        for i, h in enumerate(self.items(d.get("highlights"), f"{where}.highlights")):
            w = f"{where}.highlights[{i}]"
            h = self.keys(h, {"rect", "from", "to", "color", "shape", "grow", "pulse", "fade"}, w, ("rect",))
            a, b = self.span(h, w, n)
            s.highlights.append(Highlight(a, b, self.rect(h["rect"], f"{w}.rect"),
                                          self.color(h.get("color"), "accent", f"{w}.color"),
                                          self.enum(Shape, h.get("shape", "box"), f"{w}.shape"),
                                          bool(h.get("grow", False)), bool(h.get("pulse", True)),
                                          self.num(h.get("fade", 0.3), f"{w}.fade")))
        for i, c in enumerate(self.items(d.get("clicks"), f"{where}.clicks")):
            w = f"{where}.clicks[{i}]"
            c = self.keys(c, {"t", "at", "color"}, w, ("t", "at"))
            s.clicks.append(Click(self.num(c["t"], f"{w}.t"), self.nums(c["at"], 2, f"{w}.at"),
                                  self.color(c.get("color"), "accent", f"{w}.color")))
        for i, m in enumerate(self.items(d.get("draw"), f"{where}.draw")):
            w = f"{where}.draw[{i}]"
            m = self.keys(m, {"shape", "rect", "from", "to", "color", "width"}, w, ("rect",))
            a, b = self.span(m, w, n, end="to")
            if "to" not in m:
                b = min(a + 0.6, n)
            s.draws.append(Draw(self.enum(Shape, m.get("shape", "box"), f"{w}.shape"), self.rect(m["rect"], f"{w}.rect"),
                                a, b, self.color(m.get("color"), "mark", f"{w}.color"),
                                self.num(m.get("width", 2.0), f"{w}.width", True)))
        for i, p in enumerate(self.items(d.get("patches"), f"{where}.patches")):
            w = f"{where}.patches[{i}]"
            p = self.keys(p, {"rect", "copy", "color"}, w, ("rect",))
            s.patches.append(Patch(self.rect(p["rect"], f"{w}.rect"),
                                   self.nums(p["copy"], 2, f"{w}.copy") if "copy" in p else None,
                                   self.color(p["color"], "accent", f"{w}.color") if "color" in p else None))
        for i, t in enumerate(self.items(d.get("typing"), f"{where}.typing")):
            w = f"{where}.typing[{i}]"
            if s.image is None:
                raise ScreencastError(f"{w}: typing is rebuilt from a screenshot of the finished text; give the "
                                      "shot an `image`")
            t = self.keys(t, {"rect", "from", "to", "caret", "caret_color", "threshold"}, w, ("rect",))
            a, b = self.span(t, w, n)
            s.typing.append(Typing(self.rect(t["rect"], f"{w}.rect"), a, b, bool(t.get("caret", True)),
                                   self.color(t["caret_color"], "accent", f"{w}.caret_color")
                                   if "caret_color" in t else None,
                                   self.num(t.get("threshold", 40.0), f"{w}.threshold", True)))
        for i, x in enumerate(self.items(d.get("inserts"), f"{where}.inserts")):
            w = f"{where}.inserts[{i}]"
            x = self.keys(x, {"rect", "video", "image", "from", "to"}, w, ("rect",))
            if ("video" in x) == ("image" in x):
                raise ScreencastError(f"{w}: give exactly one of `video`, `image`")
            s.inserts.append(Insert(self.rect(x["rect"], f"{w}.rect"),
                                    self.path(x["video"], f"{w}.video") if "video" in x else None,
                                    self.path(x["image"], f"{w}.image") if "image" in x else None,
                                    self.num(x.get("from", 0.0), f"{w}.from"),
                                    self.num(x["to"], f"{w}.to") if "to" in x else None))


def style_of(override: object) -> Style:
    """`screencast:` of the settings with `override` (a shot list's `style:`) merged over it."""
    if override is not None and not isinstance(override, dict):
        raise ScreencastError("style: expected a mapping")
    base = settings.get().get("screencast")
    if not isinstance(base, dict):
        raise ScreencastError("settings.yaml has no `screencast:` section")
    try:
        return Style.parse(settings.merge(base, override or {}))
    except StyleError as e:
        raise ScreencastError(str(e)) from None


def load(path: Path) -> tuple[ShotList, Style]:
    """The shot list at `path` and its style."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ScreencastError(f"{path} not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ScreencastError(f"{path}: not valid YAML: {e}") from None
    data = Parser.keys(data, TOP_KEYS, path.name, ("shots",))
    style = style_of(data.get("style"))
    for name in ("accent", "mark", "divider"):
        if name not in style.palette:
            raise ScreencastError(f"style palette: `{name}` is required")
    p = Parser(path.parent, style)
    fade = p.num(data.get("fade", style.fade), "fade")
    shots = [p.shot(s, f"shots[{i}]", i, fade) for i, s in enumerate(p.items(data["shots"], "shots"))]
    if not shots:
        raise ScreencastError("shots: at least one shot")
    return ShotList(path, shots, data.get("style") or {}), style
