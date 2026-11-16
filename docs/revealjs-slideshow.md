# revealjs-slideshow

`docs:revealjs-slideshow` is the CLI `revealjs-slideshow.sh`, package `revealjs_slideshow_tool` (standard library
only), plus the vendored reveal.js and KaTeX in `assets/reveal.js/` and the deck template `assets/template.html`. The
vendored versions, their npm checksums, the kept files and the update procedure are in `assets/reveal.js/README.md`.

## Code

`cli.py` holds the commands `new`, `vendor`, `check` and `themes`; `deck.py` does the work. `new` refuses an unknown
theme (themes are the CSS files in `dist/theme/` of the vendored copy), copies the vendored tree into
`<dir>/reveal.js/` and fills `{{title}}` (HTML-escaped) and `{{theme}}` in the template. `vendor` deletes and recopies
`<dir>/reveal.js/`.

## check

`check_deck` parses the HTML with `html.parser` and collects the files the page loads: `src` of scripts, images,
media and iframes, `poster`, `href` of `<link>` whose `rel` includes `stylesheet`, `icon`, `preload` or
`modulepreload`, and the `data-background*` and `data-markdown` attributes of any tag. A `data-background-video` value
is split on commas. Images in inline Markdown slides (`<textarea data-template>`) are collected from Markdown image
syntax and `<img src>`.

- A remote script or stylesheet is an error, since the deck must work offline; other remote references are warnings.
- A `data-background` value that looks like a colour or gradient is not a file.
- A missing local file is an error. Paths are percent-decoded and resolved against the HTML file's directory.
- An external `data-markdown` file is a warning, since browsers block its XHR from `file://`. Its images are then
  checked against the HTML file's directory, where the slides are rendered.
- A local stylesheet that `@import`s from the network (themes with Google Fonts) is a warning.

Inline scripts are scanned as text. `RevealMath.MathJax` is an error because MathJax is not vendored.
`RevealMath.KaTeX` without a `local` key inside a `katex: { ... }` object is an error, because the math plugin then
loads KaTeX from a CDN. The object is delimited by brace matching that skips string literals, so nested objects such as
`macros` or `delimiters` do not end it early, and a `local` key outside a `katex` object is ignored. For each `local`
directory the files the plugin loads (`dist/katex.min.css`, `dist/katex.min.js`, `dist/contrib/auto-render.min.js`)
must exist. `check` exits 1 when any file has an error.

## Tests

`tests/unit/revealjs_slideshow/test_deck.py` covers `new`, `vendor`, `themes` and each `check` rule. `test_vendored.py`
checks that every `reveal.js/dist/...` and `reveal.js/plugin/...` path in `SKILL.md`, the template and `references/`
exists in the vendored copy, that those files name no CDN, `npm install` or `version: 'latest'`, that `SKILL.md` lists
every vendored theme, and that every code highlight theme in a documentation table is vendored.
