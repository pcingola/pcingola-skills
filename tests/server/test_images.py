"""`POST /v1/images/generations` and `POST /v1/images/edits` of the deployed server (docs/model_server.md, Images)
with its tiny FLUX.2 klein model, through `ai_models.images`: Pydantic-AI's OpenAI image model, and the masked
edit of `MaskedOpenAIImageModel`."""

import io

import pytest
from PIL import Image
from plugin_settings import DiffusersImageLimits
from pydantic_ai.messages import BinaryImage

from ai_models import config, images, served
from tests.media import left_half_mask, png
from tests.server.conftest import TIMEOUT_SECONDS, task

pytestmark = pytest.mark.timeout(TIMEOUT_SECONDS)


def size(data: bytes) -> tuple[int, int]:
    """The (width, height) of an image file."""
    return Image.open(io.BytesIO(data)).size


def test_image_limits_come_from_the_server():
    """`served.kind` of tasks.image is `diffusers`, and `config.image_limits` returns the limits of the server's
    entry, which the client config does not hold."""
    model = task("image")
    assert served.kind(model) == "diffusers"
    assert isinstance(config.image_limits(model, required=True), DiffusersImageLimits)


def test_generate():
    """`images.image_generator` on tasks.image answers a PNG at the `dimensions` asked for."""
    out = images.image_generator().generate_sync("a red square", settings={"dimensions": (256, 192)})
    image = out.images[0].content
    assert image.data[:8] == b"\x89PNG\r\n\x1a\n" and size(image.data) == (256, 192)


def test_edit_with_mask():
    """An edit of a reference image within a mask (the model's `inpaint` pipeline on the server) answers an image
    at the reference's size."""
    ref = BinaryImage(data=png(256, 256), media_type="image/png")
    edit = images.image_generator(task="image_edit", mask=left_half_mask(256, 256)).generate_sync(
        "a blue square", images=[ref])
    assert size(edit.images[0].content.data) == (256, 256)
