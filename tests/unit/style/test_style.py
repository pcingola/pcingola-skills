"""Unit tests for the style catalogue: the generated index and catalogue.json, one sample image per style file,
and the front matter of every style file against the tag vocabulary in SKILL.md."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from style_tool import index

SKILL_DIR = index.SKILL_DIR
ASSETS = SKILL_DIR / "assets"
GROUPS = ("technique", "mood", "colour", "detail")


def vocabulary() -> dict[str, set[str]]:
    """The `## Tags` section of SKILL.md as {group: values}."""
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    section = text.split("\n## Tags\n", 1)[1].split("\n## ", 1)[0]
    vocab = {}
    for m in re.finditer(r"^- ([a-z-]+): (.+)$", section, re.M):
        vocab[m.group(1)] = {v.strip() for v in m.group(2).split(",")}
    return vocab


class TestIndex(unittest.TestCase):

    def test_index_is_current(self) -> None:
        """references/index.md equals render_index() of the style files. Guards that the
        index is regenerated after a style file changes."""
        self.assertEqual(index.INDEX_FILE.read_text(encoding="utf-8"), index.render_index())

    def test_catalogue_is_current(self) -> None:
        """references/catalogue.json equals render_catalogue() of the style files. Guards that
        the catalogue is regenerated after a style file changes."""
        self.assertEqual(index.CATALOGUE_FILE.read_text(encoding="utf-8"), index.render_catalogue())


FIXTURE = """---
name: {name}
description: {description}
tags: [{tags}]
suits: [{suits}]
---

## Style line

A look.
"""


class TestRenderCatalogue(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.skill = Path(self.tmp.name)
        self.references = self.skill / "references"
        self.assets = self.skill / "assets"
        self.references.mkdir()
        self.assets.mkdir()
        (self.references / "index.md").write_text("# Style index\n", encoding="utf-8")
        self.add("zeta-ink", "Ink lines, café sketch.", "ink, calm", "slide")
        self.add("alpha-clay", "Clay figures.", "clay, playful", "icon, poster")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add(self, name: str, description: str, tags: str, suits: str, sample: bool = True) -> None:
        text = FIXTURE.format(name=name, description=description, tags=tags, suits=suits)
        (self.references / f"{name}.md").write_text(text, encoding="utf-8")
        if sample:
            (self.assets / f"{name}.png").write_bytes(b"png")

    def test_content(self) -> None:
        """The catalogue is a JSON array sorted by name with name, description, tags, suits
        and the sample path relative to the skill directory; non-ASCII text is kept as UTF-8,
        indent 2, trailing newline. Guards the format readers of catalogue.json parse."""
        text = index.render_catalogue(self.references)
        self.assertEqual(json.loads(text), [
            {"name": "alpha-clay", "description": "Clay figures.", "tags": ["clay", "playful"],
             "suits": ["icon", "poster"], "sample": "assets/alpha-clay.png"},
            {"name": "zeta-ink", "description": "Ink lines, café sketch.", "tags": ["ink", "calm"],
             "suits": ["slide"], "sample": "assets/zeta-ink.png"},
        ])
        self.assertIn("café", text)
        self.assertTrue(text.startswith('[\n  {\n    "name"'))
        self.assertTrue(text.endswith("]\n"))

    def test_title_and_links(self) -> None:
        """A style file's optional `title` and `links` are copied into its catalogue entry, links in file order,
        and a style without them has neither key. Guards the display name and reference links Studio shows."""
        path = self.references / "alpha-clay.md"
        text = path.read_text(encoding="utf-8").replace(
            "suits: [icon, poster]\n",
            "suits: [icon, poster]\ntitle: \"Alpha: Clay\"\nlinks:\n  Site: https://example.com/\n"
            "  Project: https://example.com/repo\n")
        path.write_text(text, encoding="utf-8")
        entries = json.loads(index.render_catalogue(self.references))
        self.assertEqual(entries[0]["title"], "Alpha: Clay")
        self.assertEqual(list(entries[0]["links"].items()),
                         [("Site", "https://example.com/"), ("Project", "https://example.com/repo")])
        self.assertNotIn("title", entries[1])
        self.assertNotIn("links", entries[1])

    def test_bad_links(self) -> None:
        """`links` that is not a mapping of label to an http(s) URL, or an empty `title`, fails naming the file.
        Guards that the catalogue never carries a link Studio cannot open."""
        path = self.references / "alpha-clay.md"
        original = path.read_text(encoding="utf-8")
        for extra in ("links: [https://example.com/]\n", "links:\n  Site: example.com\n", 'title: ""\n'):
            with self.subTest(extra=extra):
                path.write_text(original.replace("suits: [icon, poster]\n", "suits: [icon, poster]\n" + extra),
                                encoding="utf-8")
                with self.assertRaisesRegex(index.StyleError, "alpha-clay"):
                    index.render_catalogue(self.references)

    def test_missing_sample(self) -> None:
        """A style without assets/<name>.png has `"sample": null`; the other styles keep their paths. Guards
        that the catalogue never points to a missing sample and that a style without a sample is still listed."""
        self.add("mid-paper", "Paper cut.", "paper, warm", "slide", sample=False)
        entries = json.loads(index.render_catalogue(self.references))
        self.assertEqual([e["name"] for e in entries], ["alpha-clay", "mid-paper", "zeta-ink"])
        self.assertIsNone(entries[1]["sample"])
        self.assertIn('"sample": null', index.render_catalogue(self.references))
        self.assertEqual(entries[0]["sample"], "assets/alpha-clay.png")


class TestCatalogue(unittest.TestCase):

    def setUp(self) -> None:
        self.files = index.style_files()
        self.vocab = vocabulary()

    def test_vocabulary_parses(self) -> None:
        """SKILL.md's `## Tags` section has the four tag groups and `suits`. Guards the
        format the other tests parse."""
        self.assertEqual(set(self.vocab), set(GROUPS) | {"suits"})

    def test_one_png_per_style(self) -> None:
        """Every PNG has a style file (a style may have no PNG yet). Guards that samples are renamed and
        removed with their styles."""
        stems = {p.stem for p in self.files}
        pngs = {p.stem for p in ASSETS.glob("*.png")}
        self.assertTrue(stems)
        self.assertLessEqual(pngs, stems)

    def test_front_matter(self) -> None:
        """Each style file has name = file stem, a one-line description, tags with at least
        one value of each group and none outside the vocabulary, and suits from the
        vocabulary. Guards the style file format SKILL.md defines."""
        tags_all = set().union(*(self.vocab[g] for g in GROUPS))
        for path in self.files:
            with self.subTest(style=path.stem):
                meta = index.front_matter(path)
                self.assertEqual(meta.get("name"), path.stem)
                self.assertIsInstance(meta.get("description"), str)
                self.assertNotIn("\n", meta["description"].strip())
                tags = meta.get("tags")
                suits = meta.get("suits")
                self.assertIsInstance(tags, list)
                self.assertIsInstance(suits, list)
                self.assertLessEqual(set(tags), tags_all)
                for group in GROUPS:
                    self.assertTrue(set(tags) & self.vocab[group], f"no {group} tag")
                self.assertTrue(suits)
                self.assertLessEqual(set(suits), self.vocab["suits"])

    def test_sections(self) -> None:
        """Each style file has a one-line Style line and Default palette. Guards the lines
        callers put into image prompts."""
        for path in self.files:
            with self.subTest(style=path.stem):
                text = path.read_text(encoding="utf-8")
                for heading in ("Style line", "Default palette"):
                    m = re.search(rf"^## {heading}\n\n(.+)\n\n", text, re.M)
                    self.assertIsNotNone(m, heading)


if __name__ == "__main__":
    unittest.main()
