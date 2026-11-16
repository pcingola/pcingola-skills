"""The diffusers image model on the real FLUX.2 klein 4B pipeline (Hugging Face cache, about 15 GB) on the GPU,
at a small size and few steps."""

import io

import pytest
import torch
import yaml
from PIL import Image
from pydantic_ai.images import ImageGenerator
from pydantic_ai.messages import BinaryImage

from ai_models import config, local
from tests.prereq import requires

FLUX2_KLEIN = "black-forest-labs/FLUX.2-klein-4B"
INPAINT = "Flux2KleinInpaintPipeline"
SIZE = 256
HAS_GPU = torch.cuda.is_available() or torch.backends.mps.is_available()
NEEDS_GPU = requires(HAS_GPU, f"local diffusers models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")


@pytest.fixture(autouse=True)
def _config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"providers": {"local": {"kind": "diffusers", "models": {
        "klein": {"repo": FLUX2_KLEIN, "steps": 2, "guidance": 1.0, "inpaint": INPAINT}}}}}), encoding="utf-8")
    config.use(path)
    yield
    config.use(None)


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@NEEDS_GPU
def test_generation():
    gen = ImageGenerator(local.DiffusersImageModel("local:klein"))
    result = gen.generate_sync("a cat", settings={"dimensions": (SIZE, SIZE), "extra_body": {"seed": 1}})
    assert Image.open(io.BytesIO(result.image.data)).size == (SIZE, SIZE)
    assert result.image.media_type == "image/png"


@NEEDS_GPU
def test_masked_edit_runs_the_inpaint_pipeline():
    mask = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    mask.paste((0, 0, 0, 0), (0, 0, SIZE // 2, SIZE))  # transparent left half: the area to repaint
    ref = BinaryImage(data=png(Image.new("RGB", (SIZE, SIZE), "white")), media_type="image/png")
    gen = ImageGenerator(local.DiffusersImageModel("local:klein", mask=png(mask)))
    result = gen.generate_sync("a hat", images=[ref], settings={"dimensions": (SIZE, SIZE)})
    assert Image.open(io.BytesIO(result.image.data)).size == (SIZE, SIZE)
    inpaint = local.pipeline(FLUX2_KLEIN, INPAINT)  # the cached pipeline
    assert type(inpaint).__name__ == INPAINT
    assert inpaint.transformer.dtype == torch.bfloat16


@NEEDS_GPU
def test_skip_loads_components_as_none():
    """`skip` components are loaded as None, and a pipeline with and one without them are cached apart. Guards a
    model entry that leaves out a component it does not use."""
    skipped = local.pipeline(FLUX2_KLEIN, skip=["text_encoder", "tokenizer"])
    assert skipped.text_encoder is None and skipped.tokenizer is None
    assert local.pipeline(FLUX2_KLEIN) is not skipped


@NEEDS_GPU
def test_pipeline_weights_are_on_the_device():
    """`pipeline` moves every weight and buffer of each module to the device with `to_device` (docs/ai_models.md,
    Local models). Guards a weight left on the CPU after the staged copy."""
    pipe = local.pipeline(FLUX2_KLEIN)
    dev = local.device()
    for module in pipe.components.values():
        if isinstance(module, torch.nn.Module):
            assert all(t.device.type == dev for t in [*module.parameters(), *module.buffers()])
