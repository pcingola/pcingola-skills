# terminal

A terminal window floating in a night space: commands type character by character with a caret, take Enter, print their output, and the window turns to a new framing with each command. After the last command a browser window opens over it.

## When to use

- Install, setup or run steps of a tool: the commands a viewer would type, in the order they type them.
- A command whose result is a page or app: the browser ending shows it opening.
- Any scene where typed text is the subject: a query, a config line, a prompt.

## Build

- GSAP only, no images. `COMMANDS` at the top of the script holds each command: `cmd`, its start `at`, an optional typing length `dur`, an optional progress bar length `busy`, and its `out` lines (a string is muted, `[text, "ok"]` or `[text, "accent"]` is coloured).
- One paused timeline tweens a clock over the scene; `draw(t)` fills every row from `t`, so each frame is a pure function of time. The rows and their appearance times are built once at load.
- The caret is a block on the newest prompt: solid while typing, hidden from Enter to the next prompt, blinking every `BLINK` (0.53 s) while it waits.
- The window shows `ROWS` rows (8) of `LH` px (58, as `.row` in the CSS); further rows scroll it up row by row. Change `ROWS` and `LH` with the font size and the window height.
- The prompt is a plain `$`: no user, host or path. Command text is HTML-escaped.
- The entrance tweens `#term` opacity, z and y; the framings tween its rotation, x, yPercent and scale; the browser ending tweens the wrapper `#term-fx`. Two tweens on the same element and property would overlap and HyperFrames lint warns.
- The browser page is placeholder blocks. A real screenshot goes in `#page` as an `<img>` of fixed size.
- A command starts at `max(at, ready)`, where `ready` is when the previous command's last output line is on screen: a late output pushes the next command later, since rows take their place in order.
- `D` is the root's `data-duration`, which `scaffold` sets to the scene length.
- The progress bar is a CSS track and fill; block glyphs leave gaps between cells in some monospace fonts.
- Fonts: the terminal text is Noto Sans Mono (SIL OFL), 400 and 700, loaded by the two `@font-face` rules at the top from `fonts/`. After `scaffold`, copy the files into the version: `cp /usr/share/fonts/truetype/noto/NotoSansMono-{Regular,Bold}.ttf <version>/fonts/` (`fc-list : family file | grep -i "Noto Sans Mono"` gives their paths). Stills, the MP4 and film.html then draw the same font. Liberation Mono (OFL) is the fallback in the stack. Another OFL mono replaces both the `@font-face` rules and the files.

## Camera and timing

- The window floats in over 0.8 s, then turns per command: from 0.2 s before each command to 0.2 s before the next, alternating sides (rotationY plus or minus 7 degrees, x 50 px, scale rising 0.05 per command, `sine.inOut`).
- Typing: `CHAR` 0.045 s per character (about 22 characters per second) unless `dur` is set. Then `PAUSE` 0.25 s, Enter, the first output line `OUT_DELAY` 0.12 s later, the next ones `OUT_GAP` 0.09 s apart. A `busy` bar starts 0.08 s after Enter and the output follows it by 0.15 s.
- The example: commands at 0.6, 3.7 and 5.65 s; the last output is on screen at about 7.45 s (`DONE`). The browser opens at `DONE + 0.15` over 0.8 s, its blocks rise from 0.4 s later, 0.08 s apart, a light sweeps it, and it pushes in to 0.5 s before the end.
- Typing, a progress bar, output lines and the per-command framings keep every 2 s pair changing. A pause of more than about 1.5 s between commands needs a `busy` bar or a camera move.
- `OPEN_BROWSER = false`: the window pushes in to 1.12 after the last command and the caret blinks to the end.

## Narrated scene

- Key each command to the words that say it: `at: W(1, "installs") - 0.05` and `dur: WE(1, "code") - W(1, "installs")`, so the typing ends as the phrase does.
- Finish each command before its sentence ends; the output prints in the gap before the next sentence.
- A command of more than about 25 characters per second of its phrase is unreadable. Shorten it, give it its own sentence, or set `dur` to 0.05 so it appears at once and holds.
- A large final command (`/run`, `serve`) can type into a separate big line on the word that names it, as the browser opens on the next word.

## What to vary

- Palette and fonts: the `:root` variables; `--prompt`, `--caret`, `--ok` and `--accent` are the terminal colours.
- `COMMANDS`, `CHAR`, `PAUSE` and `OUT_GAP` for the tempo; `busy` for an install or a build.
- The window size (`#term`) with `ROWS`; a light theme: light `--term-bg` and `--term-bar`, dark `--ink`.
- The ending: a browser, an output file, a chart, or none.
