# Post-production: the creator credit

Every film carries the creator credit. `assemble` adds it in the same encode
that joins the scenes:

- The caption `credit.text` ("Created by <author>") in the bottom-right
  corner, small, with no box or shadow, on every scene whose template does
  not show the author itself (`shows_author`). Its colour follows the
  corner's brightness per scene: dark on a light corner, light on a dark one.
  Font, size, colours and threshold are under `credit:`.
- With `brand:` set, the brand's PNG (`raster` in `brand.yaml`) right of the
  caption, sized and spaced by the `caption` ratios in `brand.yaml`. When
  `brand.yaml` also has `raster_on_dark` (a PNG with the aspect ratio of
  `raster`), that PNG takes the same place on the scenes whose caption is in
  the light colour (dark corner); `raster` stays on the others.
  `credit.cap_height` is the cap height of `credit.font`; change it with the
  font.
- `credit.text: null`: no caption text. With a brand, the logo alone, in the
  same box (right edge on the margin, centred on the cap band of the text it
  would sit beside), on every scene including the title and end scenes, its
  PNG chosen per scene as above, from the brightness of the logo box padded
  by its height on every side instead of `credit.corner`. Without a brand,
  nothing is drawn. The end scene's credit line (`CARD.credit`) is null too.
  `credit.byline: null` leaves the title scene without a byline
  (`CARD.byline` null).
- The MP4 tags `artist` and `copyright` (`credit.copyright`).

The name is `author:`, one or more names joined with ", ".

For any other MP4, `short-video.sh credit FILE [-o OUT] --author NAME
[--author NAME ...] [--brand DIR]` writes `<name>.credit.mp4` next to the
input, or `OUT`, with the caption and tags. The video is re-encoded once,
the audio copied. `--brand` is the brand folder the brand skill reports.
`credit` reads the skill's `assets/settings.yaml`, not a project's.

## Checks before handing over

- On an image scene, the caption is readable, does not draw the eye, and
  covers nothing important. If a scene has content in that corner, move the
  content in the scene.
- The title scene shows the byline and the end scene ends on the credit line,
  unless `credit.byline` or `credit.text` is null.
- With a brand, on a 3x crop of the caption corner of a film frame
  (`ffmpeg -ss T -i film/v<N>/film.mp4 -frames:v 1 "$TMPDIR/frame.png"`), the
  logo is right of the text, unchanged in shape and colour, centred on the
  capital letters. With `raster_on_dark`, a dark scene shows that PNG and a
  light scene `raster`. The title and end scenes have no caption logo in their
  bottom corners, except with `credit.text: null`, where every scene has the
  logo and no text. The brand folder's `guidelines.md` has the brand's own
  checks.
