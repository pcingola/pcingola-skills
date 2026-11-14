# pptx-author

The design library is `plugins/media/skills/pptx-author/references/design-library/`.

## Adding a design to the design library

- A new layout is a `.md` in the shape of `layout-*.md` (when to use, center layout, design tokens) plus a `.png` guide render. It names colours by their `brand.yaml` roles (`accent1`, `accent2`, `accent3`, `dk1`, `lt1`) and holds no hex values.
- A new style exists in `brand:style` first. Its design-library file is a `.md` in the shape of `style-*.md` (catalogue style name, when to use, header, subtitle, closing, negative, center layout) plus a `.png` guide.
- Design files are brand-neutral. Brand values live in the brand folder.
