"""Image generation and edits of `ai_models` on the model server's tiny diffusers image model through a provider of
kind `openai` (`ai_models.served`): the request goes through Pydantic-AI's OpenAI image model, and the image limits
come from the server's entry."""

import io

import torch
from PIL import Image
from plugin_settings import DiffusersImageLimits
from pydantic_ai.messages import BinaryImage

from ai_models import config, images, served
from tests.integration.model_server.media import left_half_mask, png
from tests.integration.model_server_client.conftest import client_id
from tests.prereq import requires
from tests.settings_env import model_entry

NEEDS_GPU = requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
                     f"local image models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")


def size(data: bytes) -> tuple[int, int]:
    """The (width, height) of an image file."""
    return Image.open(io.BytesIO(data)).size


def test_served_image_model_runs_as_diffusers(client):
    """`served.kind` of the server's image model is `diffusers`, and `config.image_limits` returns the limits of
    the server's entry (tests/config.yaml)."""
    model = client_id("image")
    limits = config.image_limits(model, required=True)
    assert served.kind(model) == "diffusers" and isinstance(limits, DiffusersImageLimits)
    assert limits.model_dump() == model_entry("image")["image"]


@NEEDS_GPU
def test_generate_and_edit_with_mask(client):
    """`images.image_generator` generates a PNG at the `dimensions` asked for, and edits a reference image within a
    mask at the reference's size."""
    out = images.image_generator().generate_sync("a red square", settings={"dimensions": (256, 192)})
    assert size(out.images[0].content.data) == (256, 192)
    ref = BinaryImage(data=png(256, 256), media_type="image/png")
    edit = images.image_generator(task="image_edit", mask=left_half_mask(256, 256)).generate_sync(
        "a blue square", images=[ref])
    assert size(edit.images[0].content.data) == (256, 256)
