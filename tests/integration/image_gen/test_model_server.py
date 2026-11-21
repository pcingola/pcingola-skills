"""media:image-gen's `generate` on the model server's tiny diffusers image model through a provider of kind `openai`
(`ai_models.served.kind`): the request takes the diffusers settings and the server entry's image limits."""

import io

import pytest
import torch
from PIL import Image

from image_gen_tool import generate
from tests.integration.model_server_client.conftest import client  # noqa: F401 (the fixture)
from tests.prereq import requires
from tests.settings_env import model_entry

NEEDS_GPU = requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
                     f"local image models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")


@NEEDS_GPU
def test_image_gen_sizes_within_the_server_limits(client):
    """media:image-gen's `generate` on the server's model takes the diffusers sizing: `--aspect 16:9 --size 1K`
    gives a PNG whose long edge is the server entry's `max_edge`."""
    max_edge = model_entry("image")["image"]["max_edge"]
    [img] = generate.generate("a lighthouse", aspect_ratio="16:9", image_size="1K")
    w, h = Image.open(io.BytesIO(img.data)).size
    assert max(w, h) <= max_edge and w > h


def test_image_gen_refuses_png_only_options(client):
    """A transparent background is refused for the server's diffusers model before any request, as for a local
    one."""
    with pytest.raises(generate.ImageError, match="no transparent background"):
        generate.generate("a lighthouse", background="transparent")
