"""GPU-free cases of the diffusers models: mask conversion, argument order and config errors raised before any
pipeline loads. The cases that load a pipeline are in tests/integration/ai_models/test_local.py."""

import io

import pytest
from PIL import Image
from pydantic_ai.exceptions import UserError
from pydantic_ai.images import ImageGenerator
from pydantic_ai.messages import BinaryImage

from ai_models import ConfigError, local

NO_REPO = "no/such-repo"  # these cases fail before a pipeline loads


@pytest.fixture(autouse=True)
def _config(write_config):
    write_config({"diffusers": {
        "inpainter": {"repo": NO_REPO, "steps": 2, "guidance": 1.0, "inpaint": "Flux2KleinInpaintPipeline"},
        "no-inpaint": {"repo": NO_REPO, "steps": 2},
    }})


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_repaint_mask_is_white_where_transparent():
    mask = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    mask.putpixel((0, 0), (0, 0, 0, 0))
    m = local.repaint_mask(png(mask))
    assert [m.getpixel((0, 0)), m.getpixel((1, 0))] == [255, 0]


def test_mask_needs_a_reference_and_an_inpaint_pipeline():
    with pytest.raises(UserError, match="reference image"):
        ImageGenerator(local.DiffusersImageModel("inpainter", mask=b"m")).generate_sync("x")
    ref = BinaryImage(data=b"\x89PNG", media_type="image/png")
    with pytest.raises(ConfigError, match="inpaint"):
        ImageGenerator(local.DiffusersImageModel("no-inpaint", mask=b"m")).generate_sync("x", images=[ref])


def test_pipe_kwargs_order_and_optional_guidance():
    """A model entry's steps, guidance (only when set) and `args` go to the pipeline call, and the caller's arguments
    override `args` (docs/ai_models.md, `diffusers`). Guards a pipeline without `guidance_scale` and the model's
    fixed call arguments."""
    spec = {"steps": 4, "args": {"true_cfg_scale": 4.0, "max_sequence_length": 256}}
    assert local.pipe_kwargs(spec, {"max_sequence_length": 512}) == {
        "num_inference_steps": 4, "true_cfg_scale": 4.0, "max_sequence_length": 512}
    assert "guidance_scale" in local.pipe_kwargs({"steps": 1, "guidance": 1.0}, {})


def test_music_option_needs_its_argument_name(write_config):
    """A local music model takes `seconds` and `lyrics` only when its entry names their pipeline arguments
    (`duration_arg`, `lyrics_arg`); without one the option is a ConfigError before any pipeline loads. Guards a
    diffusers music pipeline with other argument names."""
    write_config({"diffusers": {"m": {"repo": NO_REPO, "steps": 1}}})
    with pytest.raises(ConfigError, match="duration_arg"):
        local.DiffusersMusicModel("m").compose("piano", seconds=10)
    with pytest.raises(ConfigError, match="lyrics_arg"):
        local.DiffusersMusicModel("m").compose("piano", lyrics="la")
