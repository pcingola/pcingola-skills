"""Scene compositions: template, `timing.js`, scaffold, static check, render.

Each scene version directory (`scenes/<scene>/v<N>/`) is a self-contained
HyperFrames project whose entry file is `index.html`. It holds its own copy of
the background PNG and of the library and kit files its page loads (`LIBS`,
`copy_page_files`) so an old version renders the same later.

Composition length: HyperFrames 0.8.143 takes the render length from the
root element's `data-duration` (with no root duration it falls back to the
GSAP timeline length, not to the clips). The root and both background clips
therefore carry `data-duration` = narration duration, marked with
`data-full-length` so `scaffold` can rewrite them when a copied `index.html`
meets a new voice version.

Starting pages live in `assets/` (`scene.html` for scenes with an image,
`scene-drawn.html` for HTML scenes without one, `<template>.html` for
template scenes). They are suggestions: the scene
author restyles each one to match the film. A template scene also gets
`card.js`, regenerated from the storyboard on every scaffold, holding the
text the page shows.

A silent HTML scene (`length` in the storyboard) has no voice version: its
`timing.json` is `{"duration": <length>, "sentences": []}`, it has no
`voice_version` file, and `render` muxes silence. A scene in a shared world
is scaffolded and rendered through its world (`world`).
"""

from __future__ import annotations

import json
import math
import os
import re
import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import determinism, media, settings, state, storyboard, versions

BACKGROUND = "background.png"
BACKGROUND_VIDEO = "background.mp4"
GSAP_REL = Path("node_modules") / "gsap" / "dist" / "gsap.min.js"
HYPERFRAMES_REL = Path("node_modules") / ".bin" / "hyperframes"
NM = Path("node_modules")


@dataclass(frozen=True)
class LibFile:
    """A pinned library file installed by `setup`: its path under the node directory and its SHA-256."""

    rel: Path
    sha256: str


# The library files a page may load with `<script src="<name>">`, by file name. Classic UMD scripts only, since
# module scripts do not load from file://. three.js stays at 0.159.0, the last release with build/three.min.js.
LIBS = {
    "gsap.min.js": LibFile(GSAP_REL, "96c01b81f44a3290e2b4532f55e2c9534b2adc43273a19f3756b2cb41f0fd0b6"),
    "anime.umd.min.js": LibFile(NM / "animejs" / "dist" / "bundles" / "anime.umd.min.js",
        "8d5b3a58a1f64023a04a4cedeef135a2263b18da04b35177ac13438a0bad033b"),
    "motion.js": LibFile(NM / "motion" / "dist" / "motion.js",
        "521cfef8910fdd997463ea9881d4b790e017331e3d2f79c02adfc4d5fe1f2cae"),
    "d3.min.js": LibFile(NM / "d3" / "dist" / "d3.min.js",
        "f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539"),
    "three.min.js": LibFile(NM / "three" / "build" / "three.min.js",
        "7b1c5d75b28d9de15042e2b374f83566d8c7146697af8fdeb4558b0fb528a585"),
}
# Classic three.js helper scripts a page loads as `<script src="kit/<file>.js">`; copied into the version's kit/.
KIT = "kit"
CARD_JS = "card.js"
# Names in a scene or world version directory that scaffold, check, stills, frames or render write. Every other
# file or directory there (fonts/, pictures, background.mp4) was added by the author and carries into the next
# version (`carry_author_files`).
GENERATED = {"index.html", "timing.js", "timing.json", "brief.md", "voice_version", CARD_JS, BACKGROUND,
             "silent.mp4", "scene.mp4", "contact.png", state.META, "world.json", KIT, "stills", "frames", *LIBS}


class SceneError(Exception):
    """A scene cannot be scaffolded or rendered."""


# ---------------------------------------------------------------------------
# Pure helpers


def norm_word(s: str) -> str:
    """Same normalisation as `norm` in timing.js."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


DRAWN = "scene-drawn"


def page_kind(scene: dict) -> str:
    """The starting page of a scene: its template, `scene` with an image,
    `scene-drawn` without one."""
    return scene.get("template") or ("scene" if scene.get("image") else DRAWN)


def _seconds_attr(duration: float | str) -> str:
    """A length as an HTML attribute value: a float at three decimals, a string as given."""
    return duration if isinstance(duration, str) else media.num(duration)


def render_template(scene_id: str, duration: float | str, kind: str = "scene") -> str:
    """The starting page `assets/<kind>.html` (`scene`, `scene-drawn`, `world` or a
    template name) with the composition id, length and frame size filled in."""
    page = settings.asset(f"{kind}.html")
    v = settings.get()["video"]
    return (
        page.replace("__SCENE_ID__", scene_id)
        .replace("__DURATION__", _seconds_attr(duration))
        .replace("__WIDTH__", str(v["width"]))
        .replace("__HEIGHT__", str(v["height"]))
        .replace("__FPS__", str(v["fps"]))
        .replace("__BACKGROUND__", BACKGROUND)
    )


def hold_seconds(scene: dict) -> float:
    """How long a template scene runs past its narration (`hold_seconds` in settings)."""
    t = scene.get("template")
    return float(settings.get()["templates"][t].get("hold_seconds", 0)) if t else 0.0


def scene_duration(scene: dict, narration_seconds: float) -> float:
    """Composition length: the narration plus the template's hold."""
    return narration_seconds + hold_seconds(scene)


def card_js(scene: dict) -> str:
    """`card.js` for a template scene: `window.CARD` with the On screen cells
    (`rows`), the author (or null), whether there is a background image, and
    the byline and credit lines from settings (null when the setting is
    null, or there is no author). The page reads its text from
    here, so a text edit in the storyboard reaches a restyled page with no
    change to `index.html`."""
    author = scene.get("author") or None
    credit = settings.get()["credit"]
    card = {"rows": [str(b) for b in scene.get("beats") or []],
            "author": author,
            "image": bool(scene.get("image")),
            "byline": credit["byline"].format(author=author) if author and credit["byline"] else None,
            "credit": credit["text"].format(author=author) if author and credit["text"] else None}
    blob = json.dumps(card, indent=1, ensure_ascii=False).replace("</", "<\\/")
    return "// Generated by short-video scaffold from the storyboard. Do not edit.\nwindow.CARD = " + blob + ";\n"


_FULL_LENGTH_TAG = re.compile(r"<[^<>]*\bdata-full-length\b[^<>]*>", re.S)
_DATA_DURATION = re.compile(r'data-duration="[^"]*"')


def set_full_length(html: str, duration: float | str) -> str:
    """Rewrite `data-duration` on every tag marked `data-full-length`."""
    value = f'data-duration="{_seconds_attr(duration)}"'
    return _FULL_LENGTH_TAG.sub(lambda m: _DATA_DURATION.sub(value, m.group(0)), html)


def timing_js(timing: dict, source: str = "") -> str:
    """`timing.js`: `window.TIMING` plus the S / SE / W / WE helpers."""
    data = {
        "duration": timing["duration"],
        "sentences": [
            {
                "index": s["index"],
                "text": s["text"],
                "start": s["start"],
                "end": s["end"],
                "words": [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in s.get("words", [])],
            }
            for s in timing["sentences"]
        ],
    }
    header = f"// Generated by short-video scaffold{' from ' + source if source else ''}. Do not edit.\n"
    return (header + "window.TIMING = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n"
            + settings.asset("timing-helpers.js"))


_CALL_RE = re.compile(r"(?<![\w$.])(STE|ST|SE|WE|S|W)\s*\(([^()]*)\)")
_INT_RE = re.compile(r"^\s*(\d+)\s*$")
_STR_RE = re.compile(r"""^\s*(["'])(.*?)\1\s*$""", re.S)


def _split_args(text: str) -> list[str]:
    args, cur, quote = [], "", None
    for ch in text:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == ",":
            args.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip() or args:
        args.append(cur)
    return args


def check_helpers(html: str, timing: dict) -> tuple[list[str], int]:
    """Verify every S/SE/W/WE call with literal arguments against `timing`.

    `timing` is a scene's `timing.json`, or a world's (`scenes`: one entry per
    scene with its `id` and `sentences`). In a world page every call names the
    scene first (`S("id", n)`, `ST("id")`); a call without a literal scene id
    as its first argument is an error, and ST/STE exist only there.

    Returns (errors, number of calls checked). Calls with non-literal
    arguments (variables, expressions) are skipped.
    """
    world = {s["id"]: s for s in timing["scenes"]} if "scenes" in timing else None
    errors: list[str] = []
    checked = 0
    for m in _CALL_RE.finditer(html):
        name, raw = m.group(1), m.group(2)
        line = html.count("\n", 0, m.start()) + 1
        args = _split_args(raw)
        where = ""
        if world is None:
            if name in ("ST", "STE"):
                errors.append(f"line {line}: {name}({raw}): {name} exists only in a world page")
                continue
            sentences = {s["index"]: s for s in timing["sentences"]}
        else:
            first = _STR_RE.match(args[0]) if args else None
            if args and _INT_RE.match(args[0]):
                errors.append(f"line {line}: {name}({raw}): a world page names the scene first, "
                              f"{name}(\"<scene id>\", ...)")
                continue
            if first is None:
                continue  # scene id is not a literal
            sid = first.group(2)
            if sid not in world:
                errors.append(f"line {line}: {name}({raw}): no scene {sid!r} in this world "
                              f"({', '.join(world)})")
                continue
            if name in ("ST", "STE"):
                if len(args) != 1:
                    errors.append(f"line {line}: {name}({raw}) takes one scene id")
                else:
                    checked += 1
                continue
            sentences = {s["index"]: s for s in world[sid]["sentences"]}
            args = args[1:]
            where = f" of scene {sid!r}"
        lead = '"scene id", ' if where else ""
        ints = [_INT_RE.match(a) for a in args]
        strs = [_STR_RE.match(a) for a in args]
        if not args or not ints[0]:
            continue  # sentence number is not a literal
        if name in ("S", "SE"):
            if len(args) != 1:
                errors.append(f"line {line}: {name}({raw}) takes {lead}one sentence number")
                continue
        else:
            if len(args) not in (2, 3) or not strs[1] or (len(args) == 3 and not ints[2]):
                if len(args) in (2, 3) and not strs[1]:
                    continue  # word is not a literal
                errors.append(f"line {line}: {name}({raw}) takes ({lead}sentence, \"word\", occurrence=1)")
                continue
        checked += 1
        n = int(ints[0].group(1))
        if n not in sentences:
            errors.append(f"line {line}: {name}({raw}): no sentence {n}{where} (scene has {len(sentences)})")
            continue
        if name in ("W", "WE"):
            word = strs[1].group(2)
            k = int(ints[2].group(1)) if len(args) == 3 else 1
            hits = [w for w in sentences[n].get("words", []) if norm_word(w["text"]) == norm_word(word)]
            if k < 1 or len(hits) < k:
                found = f"{len(hits)} occurrence(s)" if hits else "not found"
                errors.append(
                    f"line {line}: {name}({raw}): word {word!r} #{k} {found} in sentence {n}: {sentences[n]['text']}"
                )
    return errors, checked


_VIDEO_SRC = re.compile(r"""<video\b[^<>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.S | re.I)


def video_sources(html: str) -> list[str]:
    """The `src` of every `<video>` in a page."""
    return _VIDEO_SRC.findall(html)


def check_videos(sdir: Path, html: str, duration: float, fps: int) -> list[str]:
    """Every `<video>` file exists in the version directory and lasts the
    scene (`duration`, within one frame): HyperFrames stops updating a video,
    and the camera move on it, where the file ends."""
    errors = []
    for src in video_sources(html):
        path = sdir / src
        if not path.is_file():
            errors.append(f"<video src=\"{src}\">: {path} not found; copy the clip into the version directory")
        elif (length := media.video_duration(path)) < duration - 1 / fps:
            errors.append(f"<video src=\"{src}\">: {length:.2f} s is shorter than the scene ({duration:.2f} s); "
                          "pad it (ffmpeg -vf tpad=stop_mode=clone:stop_duration=S)")
    return errors


def check_background(sdir: Path, html: str, scene: dict) -> list[str]:
    """A scene page other than a template's that uses `background.png` has the
    file: a scene whose image was removed keeps the previous page, which
    still shows it. (Template pages use it only when `card.js` says so.)"""
    if scene.get("template") or BACKGROUND not in html or (sdir / BACKGROUND).is_file():
        return []
    return [f"the page uses {BACKGROUND} but the scene has no image; draw the background in the page "
            f"(see assets/{DRAWN}.html)"]


def brief_head(scene: dict, items: list[str]) -> list[str]:
    """The lines of `brief.md` up to its sentences: the title, the `items`
    (one `- ` line each) and the Brief (a template scene: the template's)."""
    template = scene.get("template")
    return [
        f"# Scene `{scene['id']}`",
        "",
        *items,
        "",
        "## Brief",
        "",
        settings.asset("template-brief.md").strip().replace("__TEMPLATE__", template)
        if template else (str(scene.get("brief") or "").strip() or "none"),
        "",
    ]


def brief_markdown(scene: dict, timing: dict, voice_version: str | None) -> str:
    """`brief.md` of a scene version; `voice_version` None for a silent scene."""
    image = f"`{scene['image']}` (copied as `{BACKGROUND}`)" if scene.get("image") else "none"
    v = settings.get()["video"]
    if timing.get("estimated"):
        narration = (f"not recorded; times estimated from the words at {timing['estimated']} words per second, "
                     f"{timing['duration']:.2f} s")
    elif voice_version:
        narration = f"voice {voice_version}, {timing['duration']:.2f} s"
    else:
        narration = f"none (silent), Length {timing['duration']:.2f} s"
    return "\n".join(brief_head(scene, [
        f"- Image: {image}",
        f"- Narration: {narration}",
        f"- Composition: {v['width']}x{v['height']}, {v['fps']} fps, id `{scene['id']}`",
    ]) + brief_sentences(scene, timing))


def brief_sentences(scene: dict, timing: dict) -> list[str]:
    """The `## Sentences and beats` lines of `brief.md`: each sentence's and
    word's times from the voice version's `timing.json`, with its beat."""
    lines = ["## Sentences and beats", ""]
    beats = scene.get("beats") or []
    for s in timing["sentences"]:
        i = s["index"]
        beat = beats[i - 1] if i - 1 < len(beats) else ""
        lines.append(f"{i}. S({i})={s['start']:.2f} to SE({i})={s['end']:.2f}: \"{s['text']}\"")
        lines.append(f"   - Beat: {beat}")
        if s.get("words"):
            words = ", ".join(f"{w['text']} {w['start']:.2f}" for w in s["words"])
            lines.append(f"   - Words: {words}")
        if s.get("aligned") is False:
            lines.append("   - Word times are estimated (alignment failed); check them at the prototype review.")
    lines.append("")
    return lines


def contact_sheet_filter(duration: float) -> str:
    """`contact_sheet:` in settings: `fps` frames per second of scene time,
    each `width` px wide, `columns` per row."""
    c = settings.get()["contact_sheet"]
    fps, width, columns = c["fps"], c["width"], c["columns"]
    frames = max(1, math.ceil(duration * fps))
    rows = max(1, math.ceil(frames / columns))
    return f"fps={fps},scale={width}:-2,tile={columns}x{rows}"


# ---------------------------------------------------------------------------
# Node / HyperFrames


def node_env(node_dir: Path, base: dict | None = None) -> dict:
    env = dict(os.environ if base is None else base)
    env["PATH"] = f"{node_dir / 'node_modules' / '.bin'}{os.pathsep}{env.get('PATH', '')}"
    env.setdefault("HYPERFRAMES_NO_TELEMETRY", "1")
    return env


NODE_FILES = ("package.json", "package-lock.json")


def _node_files_match(node_dir: Path, src: Path) -> bool:
    return all((node_dir / f).is_file() and (node_dir / f).read_bytes() == (src / f).read_bytes()
               for f in NODE_FILES)


def node_ready(node_dir: Path, src: Path | None = None) -> bool:
    """HyperFrames and GSAP are installed in `node_dir`, from the package
    files in `src` (default `node_dir` itself) when they live elsewhere."""
    if src is not None and src != node_dir and not _node_files_match(node_dir, src):
        return False
    return (node_dir / HYPERFRAMES_REL).exists() and (node_dir / GSAP_REL).is_file()


REQUIRED_DOCTOR_CHECKS = ("Node.js", "FFmpeg", "FFprobe", "Chrome")


def doctor_failures(report: dict) -> list[str]:
    """Required checks that failed or are missing from `hyperframes doctor --json`.

    Doctor's overall `ok` is false whenever an optional tool (whisper, a local
    TTS, Docker) is absent, so only the checks rendering needs are judged.
    """
    checks = {c.get("name"): c for c in report.get("checks", [])}
    failures = []
    for name in REQUIRED_DOCTOR_CHECKS:
        c = checks.get(name)
        if c is None:
            failures.append(f"{name}: not reported by doctor")
        elif not c.get("ok"):
            failures.append(f"{name}: {c.get('detail', '')} {c.get('hint', '')}".strip())
    return failures


def lib_failures(node_dir: Path) -> list[str]:
    """The `LIBS` files missing from `node_dir` or whose SHA-256 differs from the pin."""
    failures = []
    for name, lib in LIBS.items():
        f, sha = node_dir / lib.rel, lib.sha256
        if not f.is_file():
            failures.append(f"{name}: {f} missing")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != sha:
            failures.append(f"{name}: {f} SHA-256 differs from the pin {sha}")
    return failures


def setup(node_dir: Path, src: Path | None = None) -> list[str]:
    """Copy the package files from `src` (if given) into `node_dir`, then
    `npm ci`, `hyperframes browser ensure`, `hyperframes doctor`, and check the `LIBS` hashes. Returns doctor's
    check lines."""
    if src is not None and src != node_dir:
        node_dir.mkdir(parents=True, exist_ok=True)
        for f in NODE_FILES:
            shutil.copyfile(src / f, node_dir / f)
    env = node_env(node_dir)
    media.run([media.which("npm"), "ci", "--no-audit", "--no-fund"], cwd=node_dir, env=env)
    hf = str(node_dir / HYPERFRAMES_REL)
    media.run([hf, "browser", "ensure"], cwd=node_dir, env=env)
    proc = media.run([hf, "doctor", "--json"], cwd=node_dir, env=env)
    report = json.loads(proc.stdout[proc.stdout.index("{"):])
    lines = [f"{'ok ' if c.get('ok') else '-- '} {c.get('name')}: {c.get('detail', '')}" for c in report.get("checks", [])]
    failures = doctor_failures(report) + lib_failures(node_dir)
    if failures:
        raise SceneError("setup: required checks failed:\n" + "\n".join(lines + failures))
    return lines


# ---------------------------------------------------------------------------
# Scaffold / render / frames


def _latest_timing(project: Path, scene_id: str) -> tuple[Path, dict]:
    vdir = state.latest_voice(project, scene_id)
    if vdir is None:
        raise SceneError(f"scene {scene_id}: no voice yet; run `voice` first")
    return vdir, json.loads((vdir / "timing.json").read_text(encoding="utf-8"))


def silent_timing(scene: dict) -> dict:
    """`timing.json` of a silent HTML scene: its `length`, no sentences."""
    return {"duration": storyboard.length_seconds(scene), "sentences": []}


def estimated_timing(scene: dict) -> dict:
    """`timing.json` of a narrated scene without a recording: each word lasts 1 / `length.words_per_second`
    seconds, the sentences follow one another, and `estimated` holds that rate."""
    wps = float(settings.get()["length"]["words_per_second"])
    t, sentences = 0.0, []
    for i, text in enumerate(scene.get("narration") or [], 1):
        words = []
        for w in str(text).split():
            words.append({"text": w, "start": round(t, 3), "end": round(t + 1 / wps, 3)})
            t += 1 / wps
        start = words[0]["start"] if words else round(t, 3)
        sentences.append({"index": i, "text": str(text), "start": start, "end": round(t, 3), "words": words})
    return {"duration": round(t, 3), "sentences": sentences, "estimated": wps}


def scene_timing(project: Path, scene: dict, estimate: bool = False) -> tuple[Path | None, dict]:
    """(voice version, timing) of an HTML scene: the latest voice version and its timing.json, or (None,
    `silent_timing`) for a silent scene. With `estimate`, a narrated scene is timed from its words
    (`estimated_timing`) and gets no voice version."""
    if storyboard.length_seconds(scene) is not None:
        return None, silent_timing(scene)
    if estimate:
        return None, estimated_timing(scene)
    return _latest_timing(project, scene["id"])


def gsap_file(node_dir: Path) -> Path:
    """The installed `gsap.min.js`; SceneError when setup has not run."""
    gsap = node_dir / GSAP_REL
    if not gsap.is_file():
        raise SceneError(f"{gsap} missing; run `short-video.sh setup`")
    return gsap


SCRIPT_SRC = re.compile(r"""<script\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.I)


def script_sources(html: str) -> list[str]:
    """The `src` of each `<script>` of a page, without a leading `./`."""
    return [m.group(1).removeprefix("./") for m in SCRIPT_SRC.finditer(html)]


def page_files(html: str, node_dir: Path, kit_dir: Path | None = None) -> dict[str, Path]:
    """The library and kit files a page loads: relative path in the version directory -> source file. A
    `<script src>` naming a `LIBS` file maps to its file in `node_dir`; `kit/<file>.js` maps to `kit_dir`
    (default `assets/kit/`). Other sources (timing.js, card.js, the author's own files) are left out."""
    kit_dir = kit_dir or settings.ASSETS_DIR / KIT
    files = {}
    for src in script_sources(html):
        if src in LIBS:
            files[src] = node_dir / LIBS[src].rel
        elif src.startswith(KIT + "/") and "/" not in src[len(KIT) + 1:] and src.endswith(".js"):
            files[src] = kit_dir / src[len(KIT) + 1:]
    return files


def copy_page_files(out: Path, html: str, node_dir: Path, *, missing_only: bool = False,
                    kit_dir: Path | None = None) -> list[str]:
    """Copy `gsap.min.js` and every file of `page_files` into the version directory `out`. With `missing_only`
    (render) a file the directory already holds is kept. Returns the relative paths copied; SceneError when a
    source is missing."""
    kit_dir = kit_dir or settings.ASSETS_DIR / KIT
    files = {"gsap.min.js": node_dir / GSAP_REL, **page_files(html, node_dir, kit_dir)}
    copied = []
    for rel, src in files.items():
        dest = out / rel
        if missing_only and dest.is_file():
            continue
        if not src.is_file():
            kit = ", ".join(sorted(f.name for f in kit_dir.glob("*.js")))
            hint = "run `short-video.sh setup`" if rel in LIBS else f"the kit has {kit}"
            raise SceneError(f"{out / 'index.html'} loads {rel}: {src} missing; {hint}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied.append(rel)
    return copied


def composition_root(html: str) -> tuple[str | None, str]:
    """(composition id, opening tag) of the page's root: the first element with `data-composition-id`."""
    m = re.search(r"""<[a-zA-Z][^>]*\bdata-composition-id\s*=\s*["']([^"']+)["'][^>]*>""", html)
    return (m.group(1), m.group(0)) if m else (None, "")


def check_timeline(html: str) -> list[str]:
    """Errors when the page gives HyperFrames no way to seek it. A page registers `window.__timelines["<id>"]`
    (GSAP) or listens for `hf-seek` (anime.js, Motion, three.js). A root with `data-no-timeline` needs the
    `hf-seek` listener."""
    cid, tag = composition_root(html)
    if cid is None:
        return ["no element with data-composition-id"]
    seek = re.search(r"""addEventListener\(\s*["']hf-seek["']""", html) is not None
    if re.search(r"\bdata-no-timeline\b", tag):
        return [] if seek else [f'root {cid} has data-no-timeline but no window.addEventListener("hf-seek", ...)']
    registered = re.search(r"""__timelines\s*\[\s*["']""" + re.escape(cid) + r"""["']\s*\]\s*=""", html)
    if registered or seek:
        return []
    return [f'neither window.__timelines["{cid}"] = <timeline> nor an hf-seek listener; HyperFrames cannot seek '
            "the page"]


def carry_author_files(previous: Path, out: Path) -> list[str]:
    """Copy every file and subdirectory of the version directory `previous` that is not in `GENERATED`, not
    hidden and not yet in `out` into `out`. Returns the names copied."""
    copied = []
    for f in sorted(previous.iterdir()):
        if f.name in GENERATED or f.name.startswith(".") or (out / f.name).exists():
            continue
        if f.is_dir():
            shutil.copytree(f, out / f.name)
        elif f.is_file():
            shutil.copyfile(f, out / f.name)
        else:
            continue
        copied.append(f.name)
    return copied


def refresh_target(previous: Path | None, what: str) -> Path:
    """The version directory `scaffold --refresh` rewrites in place: the latest one, when it is not rendered."""
    if previous is None or not (previous / "index.html").is_file():
        raise SceneError(f"{what}: no version to refresh; run `scaffold` first")
    if (previous / "silent.mp4").is_file():
        raise SceneError(f"{previous} is rendered; run `scaffold` without --refresh for a new version")
    return previous


def scaffold(project: Path, scene: dict, node_dir: Path, refresh: bool = False, estimate: bool = False) -> Path:
    """Create the next scene version and return its directory. With `refresh`, rewrite the latest version's
    brief.md, timing files, voice_version and card.js in place instead, keeping its page and the author's files.
    With `estimate`, a narrated scene is timed from its words without a recording: its `timing.json` holds
    `estimated` (the words per second) and the version has no `voice_version`; `render` refuses it."""
    sid = scene["id"]
    if estimate and not storyboard.narrated(scene):
        raise SceneError(f"scene {sid}: --estimate applies to a narrated scene only")
    vdir, timing = scene_timing(project, scene, estimate)
    image = storyboard.image_path(project, scene["image"]) if scene.get("image") else None
    if image is not None and not image.is_file():
        raise SceneError(f"scene {sid}: image {image} not found")
    gsap_file(node_dir)

    previous = state.latest_scene(project, sid)
    out = (refresh_target(previous, f"scene {sid}") if refresh
           else versions.next_version(state.scene_root(project, sid)))
    duration = scene_duration(scene, timing["duration"])
    if previous is not None and (previous / "index.html").is_file():
        html = set_full_length((previous / "index.html").read_text(encoding="utf-8"), duration)
    else:
        html = render_template(sid, duration, page_kind(scene))
    if scene.get("template"):
        (out / CARD_JS).write_text(card_js(scene), encoding="utf-8")
    (out / "index.html").write_text(html, encoding="utf-8")
    source = (f"voice/{sid}/{vdir.name}/timing.json" if vdir
              else f"the narration's words at {timing['estimated']} words per second" if estimate
              else "the storyboard's Length")
    (out / "timing.js").write_text(timing_js(timing, source), encoding="utf-8")
    (out / "timing.json").write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if image is not None:
        shutil.copyfile(image, out / BACKGROUND)
    copy_page_files(out, html, node_dir)
    if previous is not None and previous != out:
        carry_author_files(previous, out)
    (out / "brief.md").write_text(brief_markdown(scene, timing, vdir.name if vdir else None), encoding="utf-8")
    if vdir is not None:
        (out / "voice_version").write_text(vdir.name + "\n")
    else:
        (out / "voice_version").unlink(missing_ok=True)
    return out


def _scene_voice(project: Path, sdir: Path) -> Path:
    sid = sdir.parent.name
    name = (sdir / "voice_version").read_text().strip()
    vdir = state.voice_root(project, sid) / name
    if not (vdir / "narration.wav").is_file():
        raise SceneError(f"{vdir}/narration.wav missing")
    return vdir


def silent_audio() -> list[str]:
    """FFmpeg input arguments of silence in the films' sample rate and channel layout."""
    sr = settings.get()["mix"]["sample_rate"]
    return ["-f", "lavfi", "-i", f"anullsrc=r={sr}:cl={settings.encode()['channel_layout']}"]


def voice_audio(project: Path, scene_id: str, voice_version: str | None) -> tuple[list, dict]:
    """(FFmpeg audio input, meta fields) of a scene: its voice version's narration.wav and `voice_version`, or
    silence and no field for a silent scene (`voice_version` None)."""
    if voice_version is None:
        return silent_audio(), {}
    vdir = state.voice_root(project, scene_id) / voice_version
    if not (vdir / "narration.wav").is_file():
        raise SceneError(f"{vdir}/narration.wav missing")
    return ["-i", vdir / "narration.wav"], {"voice_version": voice_version}


def lint(sdir: Path, node_dir: Path) -> dict:
    hf = str(node_dir / HYPERFRAMES_REL)
    proc = subprocess.run([hf, "lint", str(sdir), "--json"], cwd=sdir, env=node_env(node_dir),
                          text=True, capture_output=True)
    try:
        return json.loads(proc.stdout[proc.stdout.index("{"):])
    except ValueError:
        raise SceneError(f"hyperframes lint gave no JSON:\n{proc.stdout}\n{proc.stderr}") from None


def finish(sdir: Path, silent: Path, audio_input: list, meta: dict) -> Path:
    """Write `scene.mp4`, `contact.png` and `meta.json` of a rendered scene
    version from its `silent.mp4`, for every engine. `audio_input` are the
    FFmpeg input arguments of the scene's audio (the narration, or a silent
    source); the audio is padded or cut to the video length, so the scene's
    audio and video end together (`-shortest` with stream copy and apad never
    ends). `meta` (with `scene`) gets `version`, `duration`, `fps` and `rendered_at`.
    Returns scene.mp4."""
    scene_mp4 = sdir / "scene.mp4"
    ffmpeg = media.which("ffmpeg")
    e = settings.encode()
    video_len = media.num(media.video_duration(silent))
    media.run([
        ffmpeg, "-y", "-v", "error", "-i", silent, *audio_input,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-af", f"apad=whole_dur={video_len},atrim=0:{video_len}",
        "-c:a", e["audio_codec"], "-b:a", str(e["audio_bitrate"]), scene_mp4,
    ])
    duration = media.duration(scene_mp4)
    media.run([
        ffmpeg, "-y", "-v", "error", "-i", scene_mp4, "-vf", contact_sheet_filter(duration),
        "-frames:v", "1", sdir / "contact.png",
    ])
    state.write_meta(sdir, {
        "scene": meta["scene"],
        "version": sdir.name,
        **meta,
        "duration": round(duration, 3),
        "fps": settings.get()["video"]["fps"],
        "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return scene_mp4


def render(project: Path, scene: dict, node_dir: Path) -> Path:
    """Static check, lint, render, mux narration (silence for a silent scene), contact sheet, meta. Returns
    scene.mp4."""
    sid = scene["id"]
    sdir = state.latest_scene(project, sid)
    if sdir is None:
        raise SceneError(f"scene {sid}: nothing to render; run `scaffold` first")
    timing = json.loads((sdir / "timing.json").read_text(encoding="utf-8"))
    if timing.get("estimated"):
        raise SceneError(f"scene {sid}: {sdir.name} is timed from an estimate of its words; record the voice and "
                         "run `scaffold` again")
    voice_file = sdir / "voice_version"
    audio, voice_meta = voice_audio(project, sid, voice_file.read_text().strip() if voice_file.is_file() else None)
    silent = render_page(sdir, node_dir, timing, scene_duration(scene, timing["duration"]),
                         check_background(sdir, (sdir / "index.html").read_text(encoding="utf-8"), scene))
    return finish(sdir, silent, audio, {"scene": sid, **voice_meta})


def check_page(sdir: Path, node_dir: Path, timing: dict, duration: float, errors: list[str] | None = None) -> list[str]:
    """The static checks of `render` on `sdir/index.html`: helper calls against `timing`, the seekable timeline,
    the determinism rules, `<video>` files against `duration`, the caller's `errors`, then `hyperframes lint`.
    Copies a missing library or kit file the page loads. Raises SceneError on an error; returns the lint
    warnings."""
    html_path = sdir / "index.html"
    html = html_path.read_text(encoding="utf-8")
    helper_errors, _ = check_helpers(html, timing)
    if helper_errors:
        raise SceneError(f"{html_path}: timing helper calls do not match timing.json:\n" + "\n".join(helper_errors))
    errors = (check_timeline(html) + determinism.check(sdir, html, set(LIBS), KIT)
              + check_videos(sdir, html, duration, settings.get()["video"]["fps"]) + list(errors or []))
    if errors:
        raise SceneError(f"{html_path}:\n" + "\n".join(errors))
    copy_page_files(sdir, html, node_dir, missing_only=True)

    report = lint(sdir, node_dir)
    lint_errors = [f for f in report.get("findings", []) if f.get("severity") == "error"]
    if lint_errors or report.get("errorCount", 0):
        lines = [f"{f.get('code')}: {f.get('message')} ({f.get('fixHint', '')})" for f in lint_errors]
        raise SceneError("hyperframes lint errors:\n" + "\n".join(lines))
    return [f"lint warning: {f.get('code')}: {f.get('message')}" for f in report.get("findings", [])
            if f.get("severity") == "warning"]


def render_page(sdir: Path, node_dir: Path, timing: dict, duration: float, errors: list[str] | None = None) -> Path:
    """`check_page`, then render `sdir/index.html` with HyperFrames to `sdir/silent.mp4`. Returns silent.mp4."""
    for line in check_page(sdir, node_dir, timing, duration, errors):
        print(line)
    silent = sdir / "silent.mp4"
    media.run([str(node_dir / HYPERFRAMES_REL), "render", "-o", silent.name, "-q", settings.get()["render"]["quality"], "--quiet"],
              cwd=sdir, env=node_env(node_dir))
    return silent


def frames(project: Path, scene_id: str, times: list[float], version: str | None = None) -> list[Path]:
    root = state.scene_root(project, scene_id)
    sdir = root / version if version else versions.latest_version(root, require="scene.mp4")
    if sdir is None or not (sdir / "scene.mp4").is_file():
        raise SceneError(f"scene {scene_id}: no rendered version")
    out_dir = sdir / "frames"
    out_dir.mkdir(exist_ok=True)
    dur = media.duration(sdir / "scene.mp4")
    paths = []
    for t in times:
        if not 0 <= t < dur:
            raise SceneError(f"time {t} is outside the scene (0 to {dur:.2f} s)")
        p = out_dir / f"at_{t:07.3f}.png"
        media.run([media.which("ffmpeg"), "-y", "-v", "error", "-i", sdir / "scene.mp4",
                   "-ss", f"{t:.3f}", "-frames:v", "1", p])
        paths.append(p)
    return paths
