"""The operations of `edit`, parsed from a spec into typed form.

Each operation is a dataclass built from one spec object by `from_spec`, which raises
ValueError for a missing key or a value that does not convert. Its `apply` runs the
core function of the command of the same name and returns that function's result.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .cmd_add_chart import ChartAdded, add_chart
from .cmd_add_images import ImagesAdded, add_images, parse_image_paths
from .cmd_add_notes import NotesSet, PresentationNotesSetter
from .cmd_add_slide import AddedSlides, add_slides_to_file
from .cmd_add_table import PresentationTableAdder, TablesAdded
from .cmd_add_text import PresentationTextAdder, TextAdded
from .cmd_copy_slide import INVALID_INDICES_MESSAGE as INVALID_SOURCE_INDICES_MESSAGE
from .cmd_copy_slide import CopiedSlides, copy_slides
from .cmd_delete_slide import INVALID_INDICES_MESSAGE as INVALID_DELETE_INDICES_MESSAGE
from .cmd_delete_slide import DeletedSlides, delete_slides
from .common import parse_indices


class EditAction(StrEnum):
    """An `edit` action: the name of the command it runs."""
    ADD_TEXT = "add-text"
    ADD_TABLE = "add-table"
    ADD_NOTES = "add-notes"
    ADD_CHART = "add-chart"
    ADD_IMAGES = "add-images"
    ADD_SLIDE = "add-slide"
    COPY_SLIDE = "copy-slide"
    DELETE_SLIDE = "delete-slide"


def _require(spec: dict, key: str, action: EditAction):
    if key not in spec:
        raise ValueError(f"'{action}' operation requires '{key}'")
    return spec[key]


def _optional_int(value) -> int | None:
    return None if value is None else int(value)


def _comma_joined(value) -> str:
    """A list as the comma-separated string its command takes on the command line; any other value as str."""
    if isinstance(value, (list, tuple)):
        return ",".join(str(x) for x in value)
    return str(value)


def _slide_keyed(spec: dict, action: EditAction) -> dict:
    """Return the operation's `data` in the slide-N-keyed form the commands take.

    Accepts either that form directly, or a bare per-slide payload plus a `slide`
    index, the shorthand for an operation that targets one slide.
    """
    data = _require(spec, "data", action)
    if isinstance(data, dict) and any(str(k).startswith("slide-") for k in data):
        return data
    slide = _require(spec, "slide", action)
    return {f"slide-{int(slide)}": data}


@dataclass(frozen=True)
class AddTextOperation:
    """add-text: the text data, keyed by slide-N."""
    text_data: dict

    @classmethod
    def from_spec(cls, spec: dict) -> "AddTextOperation":
        return cls(_slide_keyed(spec, EditAction.ADD_TEXT))

    def apply(self, input_path: Path, output_path: Path) -> TextAdded:
        return PresentationTextAdder().add_text(input_path, self.text_data, output_path)


@dataclass(frozen=True)
class AddTableOperation:
    """add-table: the table data, keyed by slide-N."""
    table_data: dict

    @classmethod
    def from_spec(cls, spec: dict) -> "AddTableOperation":
        return cls(_slide_keyed(spec, EditAction.ADD_TABLE))

    def apply(self, input_path: Path, output_path: Path) -> TablesAdded:
        return PresentationTableAdder().add_tables(input_path, self.table_data, output_path)


@dataclass(frozen=True)
class AddNotesOperation:
    """add-notes: the notes data, keyed by slide-N."""
    notes_data: dict

    @classmethod
    def from_spec(cls, spec: dict) -> "AddNotesOperation":
        return cls(_slide_keyed(spec, EditAction.ADD_NOTES))

    def apply(self, input_path: Path, output_path: Path) -> NotesSet:
        return PresentationNotesSetter().add_notes(input_path, self.notes_data, output_path)


@dataclass(frozen=True)
class AddChartOperation:
    """add-chart: the chart data JSON, the slide index and the OBJECT placeholder index."""
    chart_config: dict
    slide: int
    index: int

    @classmethod
    def from_spec(cls, spec: dict) -> "AddChartOperation":
        action = EditAction.ADD_CHART
        chart_config = _require(spec, "data", action)
        return cls(chart_config, int(_require(spec, "slide", action)), int(spec.get("index", 0)))

    def apply(self, input_path: Path, output_path: Path) -> ChartAdded:
        return add_chart(input_path, output_path, self.slide, self.chart_config, self.index)


@dataclass(frozen=True)
class AddImagesOperation:
    """add-images: the image paths, the slide index, the placeholder type name and the index of a
    single image's placeholder (None: 0). `type` and `index` reach `add_images` as the spec gives them."""
    image_paths: list[Path]
    slide: int
    placeholder_type: str
    index: int | None

    @classmethod
    def from_spec(cls, spec: dict) -> "AddImagesOperation":
        action = EditAction.ADD_IMAGES
        images = spec.get("images", spec.get("image"))
        if images is None:
            raise ValueError(f"'{action}' operation requires 'images'")
        slide = int(_require(spec, "slide", action))
        return cls(parse_image_paths(_comma_joined(images)), slide, spec.get("type", "PICTURE"), spec.get("index"))

    def apply(self, input_path: Path, output_path: Path) -> ImagesAdded:
        return add_images(input_path, output_path, self.slide, self.image_paths, self.placeholder_type, self.index)


@dataclass(frozen=True)
class AddSlideOperation:
    """add-slide: the layout names, one new slide each, and the insert position (None: the end)."""
    layouts: list[str]
    position: int | None

    @classmethod
    def from_spec(cls, spec: dict) -> "AddSlideOperation":
        layouts = _require(spec, "layouts", EditAction.ADD_SLIDE)
        if isinstance(layouts, (list, tuple)):
            names = [str(x) for x in layouts]
        else:
            names = [n.strip() for n in str(layouts).split(",") if n.strip()]
        return cls(names, _optional_int(spec.get("position")))

    def apply(self, input_path: Path, output_path: Path) -> AddedSlides:
        return add_slides_to_file(input_path, output_path, self.layouts, self.position)


@dataclass(frozen=True)
class CopySlideOperation:
    """copy-slide: the source deck, its slide indices and the insert position in the deck being
    edited (None: the end). The deck being edited is the target."""
    source: Path
    source_indices: list[int]
    position: int | None

    @classmethod
    def from_spec(cls, spec: dict) -> "CopySlideOperation":
        action = EditAction.COPY_SLIDE
        indices = _require(spec, "source_indices", action)
        source = Path(str(_require(spec, "source", action)))
        position = _optional_int(spec.get("position"))
        return cls(source, parse_indices(_comma_joined(indices), INVALID_SOURCE_INDICES_MESSAGE), position)

    def apply(self, input_path: Path, output_path: Path) -> CopiedSlides:
        return copy_slides(self.source, input_path, output_path, self.source_indices, self.position)


@dataclass(frozen=True)
class DeleteSlideOperation:
    """delete-slide: the slide indices to remove."""
    indices: list[int]

    @classmethod
    def from_spec(cls, spec: dict) -> "DeleteSlideOperation":
        indices = spec.get("indices", spec.get("slide"))
        if indices is None:
            raise ValueError(f"'{EditAction.DELETE_SLIDE}' operation requires 'indices'")
        return cls(parse_indices(_comma_joined(indices), INVALID_DELETE_INDICES_MESSAGE))

    def apply(self, input_path: Path, output_path: Path) -> DeletedSlides:
        return delete_slides(input_path, output_path, self.indices)


EditOperation = (AddTextOperation | AddTableOperation | AddNotesOperation | AddChartOperation
                 | AddImagesOperation | AddSlideOperation | CopySlideOperation | DeleteSlideOperation)

OPERATION_TYPES: dict[EditAction, type[EditOperation]] = {
    EditAction.ADD_TEXT: AddTextOperation,
    EditAction.ADD_TABLE: AddTableOperation,
    EditAction.ADD_NOTES: AddNotesOperation,
    EditAction.ADD_CHART: AddChartOperation,
    EditAction.ADD_IMAGES: AddImagesOperation,
    EditAction.ADD_SLIDE: AddSlideOperation,
    EditAction.COPY_SLIDE: CopySlideOperation,
    EditAction.DELETE_SLIDE: DeleteSlideOperation,
}


def parse_operation(action: EditAction, spec: dict) -> EditOperation:
    """Parse one spec object of `action`; a missing key or a value that does not convert raises."""
    return OPERATION_TYPES[action].from_spec(spec)
