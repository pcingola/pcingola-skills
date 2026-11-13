# Vendored reveal.js

Copied unmodified from the npm registry tarballs; only the files a deck loads at runtime are kept.

| Package | Version | npm tarball sha512 (`dist.integrity`, verified) | License |
| --- | --- | --- | --- |
| reveal.js | 5.2.1 | `sha512-r7//6mIM5p34hFiDMvYfXgyjXqGRta+/psd9YtytsgRlrpRzFv4RbH76TXd2qD+7ZPZEbpBDhdRhJaFgfQ7zNQ==` | MIT, `LICENSE` |
| katex | 0.18.7 | `sha512-h+UCwkZ+4Jz8WQ7MLGfj7UVFrRCizGb912fwF4luGdYsC5paYG1vx+jy+KRcC/XkpjGva/P7nAWuxNnPzRvzHw==` | MIT, `plugin/math/katex/LICENSE` |

The reveal.js 5.2.1 tarball ships `dist/reveal.js` with a `reveal.js 5.2.0` banner comment; `package.json` in the same tarball says 5.2.1.

Kept from reveal.js: `dist/reveal.js`, `dist/reveal.css`, `dist/reset.css`, `dist/theme/` (with its fonts), and the UMD builds of the `markdown`, `highlight` (with `monokai.css`, `zenburn.css`), `notes` and `math` plugins. Left out: source maps, ES module builds, plugin sources, the `search` and `zoom` plugins.

Kept from KaTeX, under `plugin/math/katex/dist/`: `katex.min.js`, `katex.min.css`, `fonts/`, `contrib/auto-render.min.js`, `contrib/mhchem.min.js`. These are the paths the math plugin loads when configured with `katex: { local: 'reveal.js/plugin/math/katex' }`.

To update: `npm pack reveal.js@<ver>` and `npm pack katex@<ver>` in an empty directory, compare each tarball's sha512 with `npm view <pkg>@<ver> dist.integrity`, copy the same files, update this table, and run the `revealjs-slideshow` unit tests.
