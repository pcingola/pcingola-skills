# Brand: neutral

The neutral brand holds the colours, fonts and layout vocabulary for a deck or
figure made without a brand. It has no logo; a logo, when one is used, is
small and never the dominant element.

Files in this folder:

- `brand.yaml`: colours, fonts and the PowerPoint template.
- `pptx/presentation.pptx`: 16:9 template with the layouts "Title Slide",
  "Section Header", "Title and Content", "Two Content" and "Blank" and no
  slides. Its theme holds the colours and fonts of `brand.yaml`.
- `pptx/presentation.json`: the template description; it lists no slides.

## Colours

There are exactly three accents, plus a body grey and a caption grey. A design
uses no fourth accent.

| Key | Hex | Use |
| --- | --- | --- |
| `accent1` | `#1B1B4B` | deep indigo: primary titles, accent of the first card |
| `accent2` | `#8064A2` | muted purple: header, accent of the second card |
| `accent3` | `#6AD0DC` | soft teal: accent of the third card, hero panel borders |
| `dk1` | `#33333B` | body text, subtitles |
| `lt1` | `#FFFFFF` | background, card and panel fill |
| `caption` | `#8A8A90` | card subtitles, axis captions |
| `chip_text` | `#1F7A72` | label text on a chip |
| `chip_fill` | `#DDF0EE` | chip background (mint) |
| `neutral_chip_fill` | `#EFEFF1` | neutral chip background |
| `neutral_chip_text` | `#606068` | text on a neutral chip |

A generated image and a native slide use the same values, so both read as one
family.

## Type

Font: Calibri for headings and body (ships with Office, so a `.pptx` stays
portable). Reference sizes:

| Element | Size |
| --- | --- |
| Title | 30 pt |
| Card title | 18 pt |
| Subtitle | 14 pt |
| Claim, body | 12.5 pt |
| Chip | 10.5 pt |

## Vocabulary

- Card: white rounded rectangle with one thin coloured top accent, one small
  line icon, a bold title and one grey subtitle.
- Chip (pill): small rounded pill listing an example or a status.
- Axis: thin horizontal arrow under a row of cards with a short grey caption
  at each end; places the cards along a spectrum (for example broad to deep).
- Hero panel: taller white panel with an accent border; marks the single most
  important element.

## Canvas

Slides are 16:9: 12192000 x 6858000 EMU (13.33 x 7.5 in).
