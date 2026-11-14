"""The diffusers image model on a tiny random Stable Diffusion pipeline (429 KB, Hugging Face cache)."""

import io

import pytest
import torch
from PIL import Image
from pydantic_ai.exceptions import UserError
from pydantic_ai.images import ImageGenerator
from pydantic_ai.messages import BinaryImage

from ai_models import ConfigError, local

from .conftest import require_gpu

TINY = "dg845/tiny-random-stable-diffusion"
SIZE = 64


@pytest.fixture(autouse=True)
def _config(write_config):
    write_config({"diffusers": {
        "tiny": {"repo": TINY, "steps": 2, "guidance": 1.0, "inpaint": "StableDiffusionInpaintPipeline"},
        "tiny-no-inpaint": {"repo": TINY, "steps": 2},
    }})


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_generation():
    require_gpu()
    gen = ImageGenerator(local.DiffusersImageModel("tiny"))
    result = gen.generate_sync("a cat", settings={"dimensions": (SIZE, SIZE), "extra_body": {"seed": 1}})
    assert Image.open(io.BytesIO(result.image.data)).size == (SIZE, SIZE)
    assert result.image.media_type == "image/png"


def test_masked_edit_runs_the_inpaint_pipeline():
    require_gpu()
    mask = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    mask.paste((0, 0, 0, 0), (0, 0, SIZE // 2, SIZE))  # transparent left half: the area to repaint
    ref = BinaryImage(data=png(Image.new("RGB", (SIZE, SIZE), "white")), media_type="image/png")
    gen = ImageGenerator(local.DiffusersImageModel("tiny", mask=png(mask)))
    result = gen.generate_sync("a hat", images=[ref], settings={"dimensions": (SIZE, SIZE)})
    assert Image.open(io.BytesIO(result.image.data)).size == (SIZE, SIZE)
    inpaint = local.pipeline(TINY, "StableDiffusionInpaintPipeline")  # the cached pipeline
    assert type(inpaint).__name__ == "StableDiffusionInpaintPipeline"
    assert inpaint.unet.dtype == torch.bfloat16


def test_repaint_mask_is_white_where_transparent():
    mask = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    mask.putpixel((0, 0), (0, 0, 0, 0))
    m = local.repaint_mask(png(mask))
    assert [m.getpixel((0, 0)), m.getpixel((1, 0))] == [255, 0]


def test_mask_needs_a_reference_and_an_inpaint_pipeline():
    with pytest.raises(UserError, match="reference image"):
        ImageGenerator(local.DiffusersImageModel("tiny", mask=b"m")).generate_sync("x")
    ref = BinaryImage(data=b"\x89PNG", media_type="image/png")
    with pytest.raises(ConfigError, match="inpaint"):
        ImageGenerator(local.DiffusersImageModel("tiny-no-inpaint", mask=b"m")).generate_sync("x", images=[ref])
