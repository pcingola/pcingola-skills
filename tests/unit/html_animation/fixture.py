"""A one-chapter animation folder built from tests/data/html_animation, through the real init, add-chapter and build."""
from __future__ import annotations

import shutil
from pathlib import Path

from html_animation_tool.builder import Builder
from html_animation_tool.enums import Size, TimingLib
from html_animation_tool.project import Project

DATA = Path(__file__).resolve().parents[2] / "data" / "html_animation"


def box_project(folder: Path, lib: str = "gsap", build: bool = True) -> Project:
    """`folder` with the chapter `box` (2 s) on `lib`, at size 1:1."""
    p = Project(folder)
    p.init(TimingLib(lib), Size.SQUARE, "Box")
    p.add_chapter("box", 2)
    shutil.copyfile(DATA / "box.html", p.chapter_html("box"))
    shutil.copyfile(DATA / f"{lib}.js", p.chapter_js("box"))
    shutil.copyfile(DATA / "content.json", p.content_json)
    if build:
        Builder(p).build()
    return p
