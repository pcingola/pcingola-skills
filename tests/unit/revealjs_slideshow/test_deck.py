"""new / vendor / check on real files in a temp directory."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from revealjs_slideshow_tool import cli, deck


def run(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        try:
            cli.main(argv)
        except SystemExit as e:
            return e.code, out.getvalue()
    return 0, out.getvalue()


class TestNewDeck(unittest.TestCase):

    def test_new_deck_is_self_contained(self) -> None:
        """deck.new_deck fills the template title (HTML-escaped) and theme, copies reveal.js into the deck and the result passes check_deck. Guards the offline, self-contained deck that `new` must write."""
        with tempfile.TemporaryDirectory() as tmp:
            index = deck.new_deck(Path(tmp, "talk"), title="A & B", theme="white")
            text = index.read_text(encoding="utf-8")
            self.assertIn("<title>A &amp; B</title>", text)
            self.assertIn('href="reveal.js/dist/theme/white.css"', text)
            self.assertNotIn("{{", text)
            self.assertTrue(Path(tmp, "talk", "reveal.js", "dist", "reveal.js").is_file())
            self.assertEqual(deck.check_deck(index), [])

    def test_refuses_overwrite_without_force(self) -> None:
        """deck.new_deck raises FileExistsError on an existing index.html unless force=True. Guards against `new` overwriting a user's deck without --force."""
        with tempfile.TemporaryDirectory() as tmp:
            deck.new_deck(Path(tmp))
            with self.assertRaises(FileExistsError):
                deck.new_deck(Path(tmp))
            deck.new_deck(Path(tmp), force=True)

    def test_unknown_theme(self) -> None:
        """deck.new_deck rejects a theme not in the vendored copy. Guards against a deck linking a theme stylesheet that does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                deck.new_deck(Path(tmp), theme="nope")

    def test_every_template_reference_resolves_in_written_deck(self) -> None:
        """deck.collect_refs finds at least the template's script and stylesheet references and each resolves in a deck written by new_deck. Guards both the template paths and the parser, so check_deck on a new deck is not vacuous."""
        with tempfile.TemporaryDirectory() as tmp:
            index = deck.new_deck(Path(tmp))
            refs, _ = deck.collect_refs(index.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(refs), 9)
            for ref in refs:
                with self.subTest(ref=ref.value):
                    self.assertTrue((index.parent / ref.value).is_file())


class TestCheck(unittest.TestCase):

    def write(self, tmp, body, name="deck.html"):
        path = Path(tmp, name)
        path.write_text(f"<!doctype html><html><head>{body}</head><body></body></html>", encoding="utf-8")
        return path

    def levels(self, problems):
        return [p.level for p in problems]

    def test_missing_local_file(self) -> None:
        """deck.check_deck reports a missing local script as one error. Guards the core rule of `check`: every loaded local file must exist."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, '<script src="reveal.js/dist/reveal.js"></script>')
            problems = deck.check_deck(path)
            self.assertEqual(self.levels(problems), ["error"])
            self.assertIn("missing", problems[0].message)

    def test_vendor_fixes_missing(self) -> None:
        """deck.copy_vendor puts reveal.js next to a deck so its reveal.css and reveal.js references resolve. Guards the `vendor` command's purpose and the vendor directory name."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, '<link rel="stylesheet" href="reveal.js/dist/reveal.css">'
                                   '<script src="reveal.js/dist/reveal.js"></script>')
            deck.copy_vendor(Path(tmp))
            self.assertEqual(deck.check_deck(path), [])

    def test_remote_script_is_error(self) -> None:
        """deck.check_deck reports a remote script as an error. Guards the rule that CDN scripts and stylesheets break offline decks."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, '<script src="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.js"></script>')
            self.assertEqual(self.levels(deck.check_deck(path)), ["error"])

    def test_remote_image_is_warning_and_anchor_ignored(self) -> None:
        """deck.check_deck reports a remote image as a warning and ignores `<a href>`. Guards the error/warning split and that links are not loaded files."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, '<img src="https://example.com/a.png"><a href="https://example.com">x</a>')
            self.assertEqual(self.levels(deck.check_deck(path)), ["warning"])

    def test_google_fonts_theme_warns(self) -> None:
        """deck.check_deck warns, without errors, for a vendored theme whose CSS @imports Google Fonts. Guards the remote @import scan of local stylesheets."""
        with tempfile.TemporaryDirectory() as tmp:
            deck.copy_vendor(Path(tmp))
            path = self.write(tmp, '<link rel="stylesheet" href="reveal.js/dist/theme/night.css">')
            problems = deck.check_deck(path)
            self.assertTrue(problems)
            self.assertEqual(set(self.levels(problems)), {"warning"})

    def test_katex_without_local_is_error(self) -> None:
        """deck.check_deck reports RevealMath.KaTeX without `katex.local` as an error. Guards the rule that KaTeX must load from the vendored copy, not a CDN."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "<script>Reveal.initialize({plugins: [RevealMath.KaTeX]});</script>")
            self.assertEqual(self.levels(deck.check_deck(path)), ["error"])

    def test_katex_local_missing_files(self) -> None:
        """deck.check_deck reports one error per missing KaTeX file under a `katex.local` directory. Guards the check of the three files the math plugin appends to `local`."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "<script>Reveal.initialize({katex: {local: 'k'}, plugins: [RevealMath.KaTeX]});</script>")
            self.assertEqual(len(deck.check_deck(path)), 3)

    def test_local_outside_katex_config_ignored(self) -> None:
        """deck.check_deck ignores a `local:` key outside the `katex: {}` object and still reports KaTeX without local. Guards the scoping of the local lookup to the katex config."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "<script>Reveal.initialize({foo: {local: 'x'}, plugins: [RevealMath.KaTeX]});</script>")
            problems = deck.check_deck(path)
            self.assertEqual(len(problems), 1)
            self.assertIn("without `katex", problems[0].message)

    def test_katex_local_with_nested_macros_and_delimiters(self) -> None:
        """deck.check_deck finds `local` in a katex config with nested objects and brace characters in strings and passes with the vendored KaTeX. Guards the brace matching of katex_configs on a realistic config."""
        script = r"""<script>Reveal.initialize({
          katex: {
            macros: {"\\RR": "\\mathbb{R}", "\\set": "\\left\\{ #1 \\right\\}"},
            delimiters: [{left: '$$', right: '$$', display: true}, {left: '$', right: '$', display: false}],
            ignoredTags: ['pre', 'code'],
            local: 'reveal.js/plugin/math/katex',
            extensions: ['mhchem']
          },
          plugins: [RevealMath.KaTeX]
        });</script>"""
        with tempfile.TemporaryDirectory() as tmp:
            deck.copy_vendor(Path(tmp))
            path = self.write(tmp, script)
            self.assertEqual(deck.check_deck(path), [])

    def test_katex_configs_skips_braces_in_strings(self) -> None:
        """deck.katex_configs returns the whole katex object when string literals contain braces and ignores `local` elsewhere. Guards _object_end's string skipping."""
        script = "x = {katex: {a: '}', b: {c: \"{\"}, local: 'k'}, other: {local: 'no'}}"
        self.assertEqual(deck.katex_configs(script), ["{a: '}', b: {c: \"{\"}, local: 'k'}"])

    def test_link_rel_token_list(self) -> None:
        """deck.check_deck checks `<link>` hrefs whose rel token list contains stylesheet and skips other rels such as canonical. Guards the rel-token rule of _LINK_LOADED_RELS."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, '<link rel="alternate stylesheet" href="missing.css">'
                                   '<link rel="canonical" href="nothing.html">')
            problems = deck.check_deck(path)
            self.assertEqual(self.levels(problems), ["error"])
            self.assertIn("missing.css", problems[0].message)

    def test_missing_external_markdown(self) -> None:
        """deck.check_deck reports a missing `data-markdown` file as an error. Guards the check of external Markdown slides."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, '<section data-markdown="slides.md"></section>')
            problems = deck.check_deck(path)
            self.assertEqual(self.levels(problems), ["error"])
            self.assertIn("slides.md", problems[0].message)

    def test_external_markdown_warns_and_checks_images(self) -> None:
        """deck.check_deck warns that external Markdown needs an HTTP server and reports missing Markdown and `<img>` images inside it, not the existing one. Guards the file:// warning and the image scan of external Markdown."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "here.png").write_bytes(b"")
            Path(tmp, "slides.md").write_text(
                '## A\n![ok](here.png)\n---\n![gone](gone.png "t")\n<img src="also-gone.svg">\n', encoding="utf-8")
            path = self.write(tmp, '<section data-markdown="slides.md"></section>')
            problems = deck.check_deck(path)
            self.assertEqual(sorted(self.levels(problems)), ["error", "error", "warning"])
            text = " ".join(p.message for p in problems)
            self.assertIn("gone.png", text)
            self.assertIn("also-gone.svg", text)
            self.assertIn("http.server", text)
            self.assertNotIn("here.png", text)

    def test_inline_markdown_images(self) -> None:
        """deck.check_deck reports missing images in inline Markdown (`<textarea data-template>`) and accepts existing ones. Guards the image scan of inline Markdown slides."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "here.png").write_bytes(b"")
            path = self.write(tmp, '<section data-markdown><textarea data-template>\n'
                                   '## A\n![ok](here.png)\n![gone](img/gone.png)\n</textarea></section>')
            problems = deck.check_deck(path)
            self.assertEqual(self.levels(problems), ["error"])
            self.assertIn("img/gone.png", problems[0].message)

    def test_mathjax_is_error(self) -> None:
        """deck.check_deck reports RevealMath.MathJax as an error. Guards the rule that MathJax is not vendored and loads from a CDN."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "<script>Reveal.initialize({plugins: [RevealMath.MathJax3]});</script>")
            self.assertIn("error", self.levels(deck.check_deck(path)))

    def test_background_colour_and_video_list(self) -> None:
        """deck.check_deck treats a colour `data-background` as no file and checks each source of a comma-separated `data-background-video`. Guards both special cases in _RefParser and check_deck."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.mp4").write_bytes(b"")
            path = self.write(tmp, '<section data-background="#ff0000"></section>'
                                   '<section data-background-video="a.mp4, b.webm"></section>')
            problems = deck.check_deck(path)
            self.assertEqual(len(problems), 1)
            self.assertIn("b.webm", problems[0].message)


class TestCli(unittest.TestCase):

    def test_new_then_check(self) -> None:
        """cli `new` prints the written index path and `check` on it prints ok with exit 0. Guards the CLI contract the SKILL.md workflow relies on."""
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(["new", str(Path(tmp, "d")), "--title", "T"])
            self.assertEqual(code, 0)
            index = Path(out.strip())
            code, out = run(["check", str(index)])
            self.assertEqual(code, 0)
            self.assertIn(": ok", out)

    def test_check_fails_on_missing(self) -> None:
        """cli `check` exits 1 and prints `error: missing` for a deck with a missing script. Guards the exit code that signals a broken deck."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "x.html")
            path.write_text('<script src="reveal.js/dist/reveal.js"></script>', encoding="utf-8")
            code, out = run(["check", str(path)])
            self.assertEqual(code, 1)
            self.assertIn("error: missing", out)

    def test_themes(self) -> None:
        """cli `themes` lists the vendored themes, black among them. Guards the theme listing read from the vendored dist/theme directory."""
        code, out = run(["themes"])
        self.assertEqual(code, 0)
        self.assertIn("black", out.split())


if __name__ == "__main__":
    unittest.main()
