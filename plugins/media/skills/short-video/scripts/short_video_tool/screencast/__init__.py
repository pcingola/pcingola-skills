"""Screencast clips: screen recordings and screenshots of a software UI composed
into a video for an `Engine: clip` scene, from a YAML shot list.

A shot list is a list of shots played one after the other, each crossfaded
into the next (`fade`, 0 = a hard cut). A shot is one of:

- `panel`: a page (a recording interval re-timed to the shot's length, or a
  screenshot) as a rounded panel tilted in 3D over the background, with a soft
  shadow, an eased camera keyed in page pixels, glowing highlights, click
  ripples, typing rebuilt from the typed screenshot, marks drawn on the page,
  patches, inserted video frames and labels;
- `picture`: a picture filling the frame with an eased camera;
- `cards`: pictures as rounded cards over the background, keyed per card.

A panel or picture shot may show a before/after wipe of two pictures instead
of one source (`wipe:`), the second aligned to the first.

Modules: `compose` (camera, projection, background, panel, highlights,
labels, caption band), `sources` (video frames, pictures, alignment),
`shotlist` (the YAML format and its checks), `shots` (the renderers),
`timeline` (frame times, crossfades, the encoder). The format is documented
in the skill's `references/screencast.md`; the look (palette, background,
panel, labels, caption band, encoding quality) in `screencast:` of
`assets/settings.yaml`, which a shot list's `style:` overrides.
"""

from .shotlist import ScreencastError, load
from .timeline import render, stills

__all__ = ["ScreencastError", "load", "render", "stills"]
