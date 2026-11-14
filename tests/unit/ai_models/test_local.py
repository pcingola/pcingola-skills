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


def test_pipe_kwargs_order_and_optional_guidance():
    """A model entry's steps, guidance (only when set) and `args` go to the pipeline call, and the caller's arguments
    override `args` (docs/ai_models.md, `diffusers`). Guards a pipeline without `guidance_scale` and the model's
    fixed call arguments."""
    spec = {"steps": 4, "args": {"true_cfg_scale": 4.0, "max_sequence_length": 256}}
    assert local.pipe_kwargs(spec, {"max_sequence_length": 512}) == {
        "num_inference_steps": 4, "true_cfg_scale": 4.0, "max_sequence_length": 512}
    assert "guidance_scale" in local.pipe_kwargs({"steps": 1, "guidance": 1.0}, {})


def test_skip_loads_components_as_none():
    """`skip` components are loaded as None, and a pipeline with and one without them are cached apart. Guards a
    model entry that leaves out a component it does not use."""
    require_gpu()
    skipped = local.pipeline(TINY, skip=["safety_checker", "feature_extractor"])
    assert skipped.safety_checker is None and skipped.feature_extractor is None
    assert local.pipeline(TINY) is not skipped


def test_pipeline_weights_are_on_the_device():
    """`pipeline` moves every weight and buffer of each module to the device with `to_device` (docs/ai_models.md,
    Local models). Guards a weight left on the CPU after the staged copy."""
    require_gpu()
    pipe = local.pipeline(TINY)
    dev = local.device()
    for module in pipe.components.values():
        if isinstance(module, torch.nn.Module):
            assert all(t.device.type == dev for t in [*module.parameters(), *module.buffers()])


def test_music_option_needs_its_argument_name(write_config):
    """A local music model takes `seconds` and `lyrics` only when its entry names their pipeline arguments
    (`duration_arg`, `lyrics_arg`); without one the option is a ConfigError before any pipeline loads. Guards a
    diffusers music pipeline with other argument names."""
    write_config({"diffusers": {"m": {"repo": "no/such-repo", "steps": 1}}})
    with pytest.raises(ConfigError, match="duration_arg"):
        local.DiffusersMusicModel("m").compose("piano", seconds=10)
    with pytest.raises(ConfigError, match="lyrics_arg"):
        local.DiffusersMusicModel("m").compose("piano", lyrics="la")
