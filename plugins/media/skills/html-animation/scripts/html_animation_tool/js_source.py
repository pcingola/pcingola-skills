"""A chapter script split into code and string literals, with comments removed, for the checks of `validate`."""
from __future__ import annotations

import re
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
        self._scan()

    def _scan(self) -> None:
        t, n = self.text, len(self.text)
        out = list(t)
        i = 0
        while i < n:
            c = t[i]
            if t.startswith("//", i):
                j = t.find("\n", i)
                j = n if j < 0 else j
                self._blank(out, i, j)
                i = j
            elif t.startswith("/*", i):
                j = t.find("*/", i + 2)
                j = n if j < 0 else j + 2
                self._blank(out, i, j)
                i = j
            elif c in QUOTES:
                j = i + 1
                while j < n and t[j] != c and (c == "`" or t[j] != "\n"):
                    j += 2 if t[j] == "\\" else 1
                body = t[i + 1:min(j, n)]
                self.strings.append(JsString(i, body, c == "`" and "${" in body))
                self._blank(out, i + 1, min(j, n))
                i = j + 1
            else:
                i += 1
        self.code = "".join(out)

    @staticmethod
    def _blank(out: list[str], a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    def line(self, offset: int) -> int:
        return self.text.count("\n", 0, offset) + 1

    def string_at(self, offset: int) -> JsString | None:
        """The string literal whose opening quote is at `offset`."""
        return next((s for s in self.strings if s.start == offset), None)

    def calls(self, pattern: str) -> list[tuple[int, JsString | None]]:
        """Each match of `pattern` (a regex ending at a call's opening parenthesis) in the code, with the string
        literal that is the call's whole first argument, if any (None for `"bar-" + i`)."""
        out = []
        for m in re.finditer(pattern, self.code):
            k = self._skip(m.end())
            s = self.string_at(k)
            if s is not None and self.code[self._skip(k + len(s.value) + 2):][:1] not in (")", ","):
                s = None
            out.append((m.start(), s))
        return out

    def _skip(self, k: int) -> int:
        while k < len(self.code) and self.code[k] in " \t\r\n":
            k += 1
        return k
