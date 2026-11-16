"""A script split into code and string literals, with comments removed, for the static checks."""
from __future__ import annotations

from dataclasses import dataclass, field

QUOTES = "'\"`"


@dataclass
class JsString:
    start: int  # offset of the opening quote
    value: str
    template: bool  # a template literal holding ${...}


@dataclass
class JsSource:
    """`code`: the text with comments and string contents replaced by spaces (newlines kept, so offsets and
    line numbers hold); `strings`: the string literals."""

    text: str
    code: str = ""
    strings: list[JsString] = field(default_factory=list)

    def __post_init__(self) -> None:
        t, n = self.text, len(self.text)
        out = list(t)
        i = 0
        while i < n:
            c = t[i]
            if t.startswith("//", i):
                j = t.find("\n", i)
                j = n if j < 0 else j
                blank(out, i, j)
                i = j
            elif t.startswith("/*", i):
                j = t.find("*/", i + 2)
                j = n if j < 0 else j + 2
                blank(out, i, j)
                i = j
            elif c in QUOTES:
                j = i + 1
                while j < n and t[j] != c and (c == "`" or t[j] != "\n"):
                    j += 2 if t[j] == "\\" else 1
                body = t[i + 1:min(j, n)]
                self.strings.append(JsString(i, body, c == "`" and "${" in body))
                blank(out, i + 1, min(j, n))
                i = j + 1
            else:
                i += 1
        self.code = "".join(out)

    def line(self, offset: int) -> int:
        return self.text.count("\n", 0, offset) + 1


def blank(out: list[str], a: int, b: int) -> None:
    for k in range(a, b):
        if out[k] != "\n":
            out[k] = " "
