"""Select and order slides from a PowerPoint template to create a new presentation."""

import re
import shutil
import sys
import tempfile
import warnings
from copy import deepcopy
from pathlib import Path

from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import OpcPackage, Part
from pptx.opc.packuri import PackURI
from pptx.oxml.ns import qn

# Relationships namespace used for r:embed / r:link / r:id references in slide XML.
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Slide-level relationships not carried across decks. A notesSlide holds a
# back-reference to its own slide, so cloning it would recursively drag a
# parallel copy of the whole slide -> layout -> master -> theme tree into the
# target (duplicate parts, corrupt file). Notes are dropped on cross-deck copy.
_SKIP_SLIDE_RELTYPES = ("notesSlide",)

# Reltypes never followed when deep-copying a part's own sub-relationships.
# These point "upward" into the shared structural graph (layouts, masters,
# themes) or back at slides; each must live once in the target, not be cloned
# per referencing part.
_STRUCTURAL_RELTYPES = (
    "slide",
    "slideLayout",
    "slideMaster",
    "notesSlide",
    "notesMaster",
    "handoutMaster",
    "presentation",
    "theme",
    "tags",
)


def _next_available_slide_partname(package: OpcPackage) -> PackURI:
    """Find the next slide partname that doesn't collide with any existing part.

    After slides are deleted from a presentation, their partnames (e.g.
    /ppt/slides/slide5.xml) can be reused by add_slide() even though other
    kept slides still hold those names.  This causes duplicate entries in the
    saved ZIP and part aliasing on reload.  This function scans all parts in
    the package and returns the first unused /ppt/slides/slideN.xml name.
    """
    existing = {str(part.partname) for part in package.iter_parts()}
    n = 1
    while True:
        candidate = f"/ppt/slides/slide{n}.xml"
        if candidate not in existing:
            return PackURI(candidate)
        n += 1


def _duplicate_slide(prs, slide_index: int):
    """Duplicate a slide within the same presentation, returning the new slide.

    Works at the OPC Part level so all relationships (images, media, etc.)
    are preserved correctly.
    """
    source_slide = prs.slides[slide_index]
    src_part = source_slide.part

    # Add a new slide with the same layout to get a properly registered part
    new_slide = prs.slides.add_slide(source_slide.slide_layout)
    new_part = new_slide.part

    # Ensure the new part gets a partname that doesn't collide with any
    # existing part in the package (including slides deleted from sldIdLst
    # but still present as package parts).
    safe_name = _next_available_slide_partname(prs.part.package)
    new_part.partname = safe_name

    # Overwrite the new slide's XML with a copy of the source
    new_part._element = deepcopy(src_part._element)

    # Copy all non-layout relationships, preserving rIds
    for rel in list(new_part.rels.values()):
        if "slideLayout" not in rel.reltype:
            del new_part.rels[rel.rId]

    for rel in src_part.rels.values():
        if "slideLayout" in rel.reltype:
            continue
        if rel.is_external:
            new_part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
        else:
            new_part.rels.get_or_add(rel.reltype, rel.target_part)

    return new_slide


def _next_available_partname(package: OpcPackage, template_partname) -> PackURI:
    """Return a partname in the same directory/extension as ``template_partname``
    that no existing part in ``package`` uses.

    Media parts from different source decks routinely share names
    (``/ppt/media/image1.png`` etc.).  Reusing the source name would produce
    duplicate ZIP entries and a file LibreOffice refuses to open, so every
    cloned part is given a fresh name here.
    """
    tp = str(template_partname)
    base, dot, ext = tp.rpartition(".")
    if not dot:  # no extension
        base, ext = tp, ""
    m = re.match(r"^(.*?)(\d+)$", base)
    stem = m.group(1) if m else base + "_"
    existing = {str(part.partname) for part in package.iter_parts()}
    n = 1
    while True:
        candidate = f"{stem}{n}.{ext}" if ext else f"{stem}{n}"
        if candidate not in existing:
            return PackURI(candidate)
        n += 1


def _clone_part_into_package(src_part, package: OpcPackage, clones: dict):
    """Deep-copy an OPC part (and, recursively, the parts it relates to) into
    ``package`` under fresh, non-colliding partnames.  Returns the new Part.

    ``clones`` maps source part -> cloned part so a part referenced more than
    once (a reused image, a shared media file) is copied only once.
    """
    if src_part in clones:
        return clones[src_part]

    new_partname = _next_available_partname(package, src_part.partname)
    new_part = Part(new_partname, src_part.content_type, package, src_part.blob)
    clones[src_part] = new_part

    for rel in src_part.rels.values():
        if any(rel.reltype.endswith(x) for x in _STRUCTURAL_RELTYPES):
            continue
        if rel.is_external:
            new_part.relate_to(rel.target_ref, rel.reltype, is_external=True)
        else:
            sub = _clone_part_into_package(rel.target_part, package, clones)
            new_part.relate_to(sub, rel.reltype)

    return new_part


def _remap_rids(element, rId_map: dict) -> None:
    """Rewrite r:id / r:embed / r:link attributes in ``element`` (a deep-copied
    slide XML tree) from source rIds to the rIds they were given in the target
    part.  Without this the copied XML still points at the source's rId scheme
    and images/media fail to resolve."""
    if not rId_map:
        return
    prefix = "{" + _R_NS + "}"
    for el in element.iter():
        for name, value in list(el.attrib.items()):
            if name.startswith(prefix) and value in rId_map:
                el.set(name, rId_map[value])


def _target_layout_for(source_slide, target_presentation):
    """Pick a layout that lives in the TARGET package for a cloned slide.

    Relating the new slide to the *source's* layout would pull the source
    layout, its master and theme (all with colliding partnames) into the
    target.  Image-gen / authored decks carry all visible content on the slide
    itself, so any target layout of the same name works; fall back to the layout
    of an existing target slide, then to the first available layout.
    """
    src_name = source_slide.slide_layout.name
    for master in target_presentation.slide_masters:
        for layout in master.slide_layouts:
            if layout.name == src_name:
                return layout
    if len(target_presentation.slides):
        return target_presentation.slides[0].slide_layout
    return target_presentation.slide_masters[0].slide_layouts[0]


def clone_slide_to_presentation(source_presentation, target_presentation, source_index: int,
                                position: int | None = None):
    """Clone a slide from source to target presentation, preserving relationships.

    Copies the slide XML and deep-copies every part it references (images,
    media, embedded objects) into the target package under fresh partnames,
    remapping the rId references so the result is valid across independently
    authored decks — no duplicate ZIP entries, no cross-package part sharing.

    `position` is a 0-based index in the target's slide list. The slide is
    always appended first, then moved; None leaves it appended.
    """
    source_slide = source_presentation.slides[source_index]
    src_part = source_slide.part
    package = target_presentation.part.package

    layout = _target_layout_for(source_slide, target_presentation)
    new_slide = target_presentation.slides.add_slide(layout)
    new_part = new_slide.part

    # Ensure unique partname (see _duplicate_slide for explanation)
    new_part.partname = _next_available_slide_partname(package)

    # Copy of the source slide XML; rId references get remapped below.
    new_element = deepcopy(src_part._element)

    # The layout rId that add_slide() just created on the fresh part; keep it.
    new_layout_rId = next(
        (rel.rId for rel in new_part.rels.values() if "slideLayout" in rel.reltype),
        None,
    )

    # Drop every non-layout rel the fresh part came with.
    for rel in list(new_part.rels.values()):
        if "slideLayout" not in rel.reltype:
            del new_part.rels[rel.rId]

    # Recreate each source relationship, cloning internal parts into the target
    # package, and record source-rId -> new-rId so the XML can be remapped.
    clones: dict = {}
    rId_map: dict = {}
    for rel in src_part.rels.values():
        if "slideLayout" in rel.reltype:
            if new_layout_rId is not None:
                rId_map[rel.rId] = new_layout_rId
            continue
        if any(rel.reltype.endswith(x) for x in _SKIP_SLIDE_RELTYPES):
            continue
        if rel.is_external:
            rId_map[rel.rId] = new_part.relate_to(
                rel.target_ref, rel.reltype, is_external=True
            )
        else:
            cloned = _clone_part_into_package(rel.target_part, package, clones)
            rId_map[rel.rId] = new_part.relate_to(cloned, rel.reltype)

    _remap_rids(new_element, rId_map)
    new_part._element = new_element

    if position is not None:
        move_slide_to_position(target_presentation, position)

    return new_slide


def move_slide_to_position(presentation, position: int) -> None:
    """Move the last slide of `presentation` to 0-based `position`.

    python-pptx has no insert-at-index; add_slide always appends. Reordering
    `sldIdLst` afterwards is the whole mechanism — the same one
    `create_presentation_from_template` uses for its phase-3 reorder.
    """
    sldIdLst = presentation.slides._sldIdLst
    appended_at = len(sldIdLst) - 1
    if not 0 <= position <= appended_at:
        raise ValueError(f"Insert position {position} out of range (0-{appended_at})")
    if position == appended_at:
        return
    element = sldIdLst[appended_at]
    sldIdLst.remove(element)
    sldIdLst.insert(position, element)


def create_presentation_from_template(template_path: Path, output_path: Path, sequence: list[int]) -> int:
    """Create presentation with selected slides in specified order.

    Strategy: copy the template, then manipulate slides in-place.
    - Unique indices: keep those slides, delete the rest, reorder.
    - Duplicate indices: duplicate slides within the presentation.

    Returns the number of slides in the saved presentation. This function
    intentionally does not print — it's a library routine. The CLI
    wrapper `run_select_slides` is responsible for any user-facing output.
    """
    template = Presentation(str(template_path))
    total_slides = len(template.slides)

    # Validate sequence
    for idx in sequence:
        if not 0 <= idx < total_slides:
            raise ValueError(f"Slide index {idx} out of range (0-{total_slides - 1})")

    # Create temporary copy to preserve the template file
    with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        shutil.copy2(template_path, tmp_path)
        prs = Presentation(str(tmp_path))

        # Phase 1: delete slides not referenced in sequence
        unique_indices = set(sequence)
        to_delete = sorted(
            [i for i in range(total_slides) if i not in unique_indices],
            reverse=True,
        )
        for idx in to_delete:
            remove_slide(prs, idx)

        # Build a map from original index -> current position after deletions
        kept = sorted(unique_indices)
        orig_to_current = {orig: cur for cur, orig in enumerate(kept)}

        # Phase 2: duplicate slides where needed (indices appearing more than once)
        # We process duplicates at the end of the slide list, then reorder everything.
        from collections import Counter
        counts = Counter(sequence)
        # For indices that appear more than once, duplicate them
        for orig_idx in kept:
            for _ in range(counts[orig_idx] - 1):
                _duplicate_slide(prs, orig_to_current[orig_idx])

        # Phase 3: reorder sldIdLst to match the requested sequence
        sldIdLst = prs.slides._sldIdLst
        entries = list(sldIdLst)

        # Build mapping: each entry's original index
        # First len(kept) entries are the originals (in sorted order of kept),
        # remaining entries are duplicates appended in order of (kept iteration)
        entry_orig_indices = list(kept)  # originals
        for orig_idx in kept:
            for _ in range(counts[orig_idx] - 1):
                entry_orig_indices.append(orig_idx)

        # For each position in sequence, pick the right entry
        # Track how many times each orig_idx has been consumed
        consumed = {idx: 0 for idx in unique_indices}
        # Build entry pools: for each orig_idx, list of entries
        pools = {idx: [] for idx in unique_indices}
        for entry, orig_idx in zip(entries, entry_orig_indices):
            pools[orig_idx].append(entry)

        ordered_entries = []
        for orig_idx in sequence:
            entry = pools[orig_idx][consumed[orig_idx]]
            consumed[orig_idx] += 1
            ordered_entries.append(entry)

        # Clear and re-add in order
        for entry in entries:
            sldIdLst.remove(entry)
        for entry in ordered_entries:
            sldIdLst.append(entry)

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='Duplicate name:')
            prs.save(str(output_path))
        return len(prs.slides)

    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def parse_sequence(sequence_str: str) -> list[int]:
    """Parse comma-separated indices into integer list."""
    try:
        return [int(x.strip()) for x in sequence_str.split(",")]
    except ValueError:
        raise ValueError("Invalid sequence format. Use comma-separated integers (e.g., 0,34,34,50,52)")


def remove_slide(presentation, index: int) -> None:
    """Remove a slide from presentation."""
    rel_id = presentation.slides._sldIdLst[index].rId
    presentation.part.drop_rel(rel_id)
    del presentation.slides._sldIdLst[index]


def run_select_slides(args) -> None:
    """Entry point from CLI dispatcher."""
    try:
        template_path = Path(args.template)
        output_path = Path(args.output)

        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")

        sequence = parse_sequence(args.sequence)
        print(f"Creating presentation with {len(sequence)} slides...")
        for i, source_idx in enumerate(sequence):
            print(f"  [{i}] Slide {source_idx}")
        final_count = create_presentation_from_template(template_path, output_path, sequence)
        print(f"\nSaved to: {output_path}")
        print(f"Final presentation: {final_count} slides")

    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error processing presentation: {e}", file=sys.stderr)
        sys.exit(1)
