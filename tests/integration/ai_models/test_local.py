"""The diffusers image model of the `image` task of tests/config.yaml (tiny, random weights, with an `inpaint`
pipeline) on the GPU, at a small size and few steps."""

import io

import pytest
import torch
from PIL import Image
from pydantic_ai.images import ImageGenerator
from pydantic_ai.messages import BinaryImage

from ai_models import config, local
from tests.prereq import requires
from tests.settings_env import TEST_CONFIG, task_model

MODEL = task_model("image")
SIZE = 256
HAS_GPU = torch.cuda.is_available() or torch.backends.mps.is_available()
NEEDS_GPU = requires(HAS_GPU, f"local diffusers models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")


@pytest.fixture(autouse=True)
def spec():
    """The `DiffusersModel` entry of MODEL, with TEST_CONFIG in use for the test."""
    config.use(TEST_CONFIG)
    yield local.DiffusersImageModel(MODEL).spec
    config.use(None)


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@NEEDS_GPU
def test_generation():
    """`DiffusersImageModel` generates one PNG at the requested dimensions through Pydantic-AI's `ImageGenerator`."""
    gen = ImageGenerator(local.DiffusersImageModel(MODEL))
    result = gen.generate_sync("a cat", settings={"dimensions": (SIZE, SIZE), "extra_body": {"seed": 1}})
    assert Image.open(io.BytesIO(result.image.data)).size == (SIZE, SIZE)
    assert result.image.media_type == "image/png"


@NEEDS_GPU
def test_masked_edit_runs_the_inpaint_pipeline(spec):
    """A mask sends the edit to the model's `inpaint` pipeline, built from the base pipeline in bfloat16."""
    mask = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    mask.paste((0, 0, 0, 0), (0, 0, SIZE // 2, SIZE))  # transparent left half: the area to repaint
    ref = BinaryImage(data=png(Image.new("RGB", (SIZE, SIZE), "white")), media_type="image/png")
    gen = ImageGenerator(local.DiffusersImageModel(MODEL, mask=png(mask)))
    result = gen.generate_sync("a hat", images=[ref], settings={"dimensions": (SIZE, SIZE)})
    assert Image.open(io.BytesIO(result.image.data)).size == (SIZE, SIZE)
    inpaint = local.pipeline(spec.repo, spec.inpaint)  # the cached pipeline
    assert type(inpaint).__name__ == spec.inpaint
    assert inpaint.transformer.dtype == torch.bfloat16


@NEEDS_GPU
def test_skip_loads_components_as_none(spec):
    """`skip` components are loaded as None, and a pipeline with and one without them are cached apart. Guards a
    model entry that leaves out a component it does not use."""
    skipped = local.pipeline(spec.repo, skip=["text_encoder", "tokenizer"])
    assert skipped.text_encoder is None and skipped.tokenizer is None
    assert local.pipeline(spec.repo) is not skipped


@NEEDS_GPU
def test_pipeline_weights_are_on_the_device(spec):
    """`pipeline` moves every weight and buffer of each module to the device with `to_device` (docs/ai_models.md,
    Local models). Guards a weight left on the CPU after the staged copy."""
    pipe = local.pipeline(spec.repo)
    dev = local.device()
    for module in pipe.components.values():
        if isinstance(module, torch.nn.Module):
            assert all(t.device.type == dev for t in [*module.parameters(), *module.buffers()])
