"""Unit tests for pptx-author.

The skill carries no code: it is SKILL.md and references/. Its template path fills the
`neutral` brand's presentation template from the brand plugin. So the unit suite tests that
template and the one reference block copied by hand out of it: the slot map in
references/03-layout-mapping.md.

The suite runs in the `pptx` skill's project (`uv run --project plugins/docs/skills/pptx/scripts`), so it builds
slides with `pptx_tool` the way `docs:pptx` does.
"""
