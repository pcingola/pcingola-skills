"""Every reveal.js path the skill ships or documents resolves to a vendored file."""
import re
import unittest

from revealjs_slideshow_tool import deck

# `reveal.js/dist/...` or `reveal.js/plugin/...` as written in templates and docs
REF = re.compile(r"""reveal\.js/((?:dist|plugin)/[^\s"'`)<>|]+)""")
THEME_PLACEHOLDER = "dist/theme/{{theme}}.css"


def shipped_text_files():
    skill = deck.SKILL_DIR
    return [skill / "SKILL.md", deck.TEMPLATE, *sorted((skill / "references").glob("*.md"))]


class TestVendoredReferences(unittest.TestCase):

    def test_every_documented_path_exists(self) -> None:
        """Every `reveal.js/dist/...` or `reveal.js/plugin/...` path in SKILL.md, the deck template and references/ exists in the vendored copy, and the core files are among them. Guards against docs or template naming a file the vendored copy lacks."""
        checked = set()
        for path in shipped_text_files():
            for rel in REF.findall(path.read_text(encoding="utf-8")):
                rel = rel.rstrip(".,;:")
                if rel == THEME_PLACEHOLDER:
                    continue
                checked.add(rel)
                with self.subTest(file=path.name, ref=rel):
                    target = deck.VENDOR_DIR / rel
                    # `plugin/math/katex` is a directory (the KaTeX `local` option)
                    self.assertTrue(target.exists(), f"{path.name}: {rel} not in {deck.VENDOR_DIR}")
        for rel in ("dist/reveal.js", "dist/reveal.css", "plugin/markdown/markdown.js",
                    "plugin/highlight/highlight.js", "plugin/notes/notes.js", "plugin/math/math.js"):
            self.assertIn(rel, checked)

    def test_no_cdn_or_npm_instructions(self) -> None:
        """SKILL.md, the template and references/ contain no CDN URL, npm install or `version: 'latest'`. Guards the skill's offline-only rule."""
        for path in shipped_text_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotIn("cdn.jsdelivr", text)
                self.assertNotIn("unpkg.com", text)
                self.assertNotIn("npm install", text)
                self.assertNotIn("version: 'latest'", text)

    def test_skill_md_lists_every_vendored_theme(self) -> None:
        """The SKILL.md Themes section names every theme deck.themes() finds. Guards SKILL.md against drifting from the vendored themes."""
        text = (deck.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        section = text.split("### Themes", 1)[1].split("###", 1)[0]
        listed = set(re.findall(r"[a-z_-]+", section.split("\n\n", 1)[0]))
        for theme in deck.themes():
            self.assertIn(theme, listed)

    def test_documented_code_themes_are_vendored(self) -> None:
        """Every code highlight theme in a documentation table exists as a vendored highlight CSS. Guards against documenting a highlight theme that is not shipped."""
        vendored = {p.stem for p in (deck.VENDOR_DIR / "plugin" / "highlight").glob("*.css")}
        for path in shipped_text_files():
            for theme in re.findall(r"^\| (\w+) \| `#[0-9a-fA-F]{6}` \|$", path.read_text(encoding="utf-8"), re.M):
                with self.subTest(file=path.name, theme=theme):
                    self.assertIn(theme, vendored)


if __name__ == "__main__":
    unittest.main()
