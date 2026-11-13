---
name: revealjs-slideshow
description: "Creates offline reveal.js HTML presentations with Markdown, code highlighting, animations, themes, speaker notes and math. TRIGGER when: user asks for a slideshow, presentation or HTML slides, or mentions reveal.js, revealjs or an .html deck."
allowed-tools: Bash(scripts/revealjs-slideshow.sh:*) Bash(${CLAUDE_SKILL_DIR}/scripts/revealjs-slideshow.sh:*)
---

# Reveal.js Slideshow

Create and maintain HTML presentations with reveal.js. The skill ships reveal.js 5.2.1 (with the `markdown`, `highlight`, `notes` and `math` plugins and KaTeX) in `assets/reveal.js/`; versions and checksums are in `assets/reveal.js/README.md`.

## Decks are self-contained

A deck is a directory: `index.html` plus a copy of the vendored reveal.js in `reveal.js/` next to it. Every path in the HTML is relative (`reveal.js/dist/reveal.css`, `reveal.js/plugin/...`), so the directory works offline, from `file://`, and can be zipped or moved. Write Markdown slides inline (`<section data-markdown><textarea data-template>`): an external file (`data-markdown="slides.md"`) is loaded by XHR, which browsers block from `file://`, so it works only when the deck directory is served over HTTP (`python3 -m http.server` in it, then open `http://localhost:8000/`). Never link reveal.js, plugins or KaTeX from a CDN and never install them with npm.

```bash
# New deck: writes <dir>/index.html from assets/template.html and copies reveal.js into <dir>/reveal.js/
${CLAUDE_SKILL_DIR}/scripts/revealjs-slideshow.sh new <dir> --title "My Talk" --theme black

# Existing HTML deck: copy (or refresh) reveal.js next to it
${CLAUDE_SKILL_DIR}/scripts/revealjs-slideshow.sh vendor <dir>

# After every edit: every script, stylesheet, image and KaTeX file must exist locally (exit 1 otherwise)
${CLAUDE_SKILL_DIR}/scripts/revealjs-slideshow.sh check <dir>/index.html

# Vendored theme names
${CLAUDE_SKILL_DIR}/scripts/revealjs-slideshow.sh themes
```

`check` reports as errors: a missing local file (including a `data-markdown` file and images inside Markdown slides), a remote `<script>` or stylesheet, `RevealMath.KaTeX` without `katex: { local: ... }`, and MathJax (not vendored). It warns about remote media, external Markdown files (need HTTP) and themes that `@import` Google Fonts. Images, videos and Markdown files used by the deck go inside the deck directory too.

## Instructions

1. **Gather requirements**: topic, structure, audience; content format (HTML, Markdown or both); code highlighting; speaker notes; theme and transitions.
2. **Create the deck** with `new <dir>`. The template loads all four plugins and shows one slide of each kind; replace the slides.
3. **Write slides** in `<dir>/index.html`, HTML or inline Markdown (`<textarea data-template>`). Use an external `data-markdown="slides.md"` only when the deck will be served over HTTP.
4. **Configure** transitions, navigation and size in `Reveal.initialize`. Keep `katex: { local: 'reveal.js/plugin/math/katex' }` if math is used.
5. **Check** with `check <dir>/index.html` and fix every error.
6. **Open** the deck in a browser (`open <dir>/index.html` on macOS) to review it.

### Basic template

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>My Presentation</title>
    <link rel="stylesheet" href="reveal.js/dist/reveal.css">
    <link rel="stylesheet" href="reveal.js/dist/theme/black.css">
  </head>
  <body>
    <div class="reveal">
      <div class="slides">
        <section>Slide 1</section>
        <section>Slide 2</section>
      </div>
    </div>
    <script src="reveal.js/dist/reveal.js"></script>
    <script>
      Reveal.initialize();
    </script>
  </body>
</html>
```

The full template with all plugins is `assets/template.html`.

### Vertical slides

```html
<section>
  <section>Main Topic</section>
  <section>Sub-topic 1</section>
  <section>Sub-topic 2</section>
</section>
```

## Quick reference

### Themes
black (default), white, league, beige, sky, night, serif, simple, solarized, blood, moon, dracula, black-contrast, white-contrast, white_contrast_compact_verbatim_headers.

`black`, `white`, `serif`, `dracula` and the contrast themes use only local fonts. `beige`, `blood`, `league`, `moon`, `night`, `simple`, `sky` and `solarized` import a font from Google Fonts; offline the browser falls back to a system font. Prefer the local-font themes when the deck must look the same offline.

### Transitions
none, fade, slide, convex, concave, zoom

### Fragment types
fade-in, fade-out, fade-up, highlight-red, highlight-green, highlight-blue, fade-in-then-out

### Plugins
| Plugin | Purpose | Include |
|:-------|:--------|:--------|
| RevealMarkdown | Markdown slides | `reveal.js/plugin/markdown/markdown.js` |
| RevealHighlight | Code highlighting | `reveal.js/plugin/highlight/highlight.js` + `reveal.js/plugin/highlight/monokai.css` |
| RevealNotes | Speaker notes | `reveal.js/plugin/notes/notes.js` |
| RevealMath.KaTeX | Math formulas | `reveal.js/plugin/math/math.js` + `katex: { local: 'reveal.js/plugin/math/katex' }` |

### Key attributes
| Attribute | Purpose |
|:----------|:--------|
| `data-markdown` | Enable Markdown in section |
| `data-trim` | Remove code indentation |
| `data-line-numbers` | Show/highlight line numbers |
| `data-auto-animate` | Animate between slides |
| `data-transition` | Per-slide transition |
| `data-background` | Slide background |

## Critical notes

### Step-by-step code highlighting

With `data-line-numbers="1-2|3|4"`, give the code an opaque background or the steps stack visually:

```css
.reveal pre code.hljs { background: #272822; } /* monokai */
```

Theme colours: monokai `#272822`, zenburn `#3f3f3f`.

### Speaker view
Press `S` during the presentation to open the speaker view with notes and timer.

### PDF export
Add `?print-pdf` to the URL, then use the browser print dialog.

## Guidelines

**Content structure**: horizontal slides for main sections, vertical slides for sub-topics, fragments for progressive reveal, one idea per slide.

**Code**: always `data-trim`; use line highlighting to focus attention; match the code theme to the slide theme.

**Practice**: load CSS before JavaScript; test the speaker view before presenting; use animations sparingly; keep fonts readable and contrast high.

## Detailed reference

Code examples, API methods and configuration options: [references/REFERENCE.md](references/REFERENCE.md).
