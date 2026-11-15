"""A chapter's html parsed into its elements and style text, for the checks of `validate`."""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    line: int


@dataclass
class StyleBlock:
    text: str
    line: int


class ChapterHtml(HTMLParser):
    """Elements in document order and the text of each `<style>` block."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self.styles: list[StyleBlock] = []
        self._in_style: int | None = None
        self._style_text: list[str] = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        self.elements.append(Element(tag, {k: v or "" for k, v in attrs}, line))
        if tag == "style":
            self._in_style = line
            self._style_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append(Element(tag, {k: v or "" for k, v in attrs}, self.getpos()[0]))

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._in_style is not None:
            self.styles.append(StyleBlock("".join(self._style_text), self._in_style))
            self._in_style = None

    def handle_data(self, data: str) -> None:
        if self._in_style is not None:
            self._style_text.append(data)

    @property
    def ids(self) -> dict[str, int]:
        """Each id and the line of its first element."""
        out: dict[str, int] = {}
        for e in self.elements:
            if e.attrs.get("id"):
                out.setdefault(e.attrs["id"], e.line)
        return out
