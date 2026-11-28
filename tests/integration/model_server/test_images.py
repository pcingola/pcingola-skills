"""`POST /v1/images/generations` and `POST /v1/images/edits` of the model server (docs/model_server.md, Images)
through the `openai` SDK, on the tiny random-weight image model of tests/config.yaml, in process on the GPU."""

import base64
import io

import openai
import pytest
import torch
from PIL import Image

from tests.media import left_half_mask, png
from tests.prereq import requires
from tests.settings_env import task_model

MODEL = task_model("image")
SIZE = 256
NEEDS_GPU = requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
                     f"local diffusers models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")


def sizes(response) -> list[tuple[int, int]]:
    """The (width, height) of each b64_json PNG of an `ImagesResponse`."""
    return [Image.open(io.BytesIO(base64.b64decode(d.b64_json))).size for d in response.data]


@NEEDS_GPU
def test_generation_with_size_n_and_seed(running):
    """`images.generate` answers `n` PNGs at `size` from one pipeline call; `seed` (an `extra_body` field) goes to
    the pipeline, so the same seed gives the same image."""
    def generate(n: int, seed: int):
        return running.client.images.generate(model=MODEL, prompt="a red cat", size=f"{SIZE}x{SIZE}", n=n,
                                              extra_body={"seed": seed})

    two = generate(2, 1)
    assert sizes(two) == [(SIZE, SIZE)] * 2 and two.output_format == "png"
    assert generate(1, 7).data[0].b64_json == generate(1, 7).data[0].b64_json


@NEEDS_GPU
def test_edit_with_mask_and_with_two_references(running):
    """`images.edit` with a mask runs the model's inpaint pipeline on the reference image; with two reference
    images and no mask, both go to the pipeline. Each answers one PNG at `size`."""
    masked = running.client.images.edit(model=MODEL, prompt="a hat", size=f"{SIZE}x{SIZE}",
                                        image=("ref.png", png(SIZE, SIZE, "white"), "image/png"),
                                        mask=("mask.png", left_half_mask(SIZE, SIZE), "image/png"))
    assert sizes(masked) == [(SIZE, SIZE)]
    refs = [("a.png", png(SIZE, SIZE, "white"), "image/png"), ("b.png", png(SIZE, SIZE, "blue"), "image/png")]
    multi = running.client.images.edit(model=MODEL, prompt="the two together", size=f"{SIZE}x{SIZE}", image=refs)
    assert sizes(multi) == [(SIZE, SIZE)]


def test_wrong_role_and_unknown_model_are_openai_errors(running):
    """A local model of another role is a 400 and an unknown model of a local provider a 404, each as an OpenAI
    error body the SDK reads (`code`), before any model loads."""
    with pytest.raises(openai.BadRequestError) as e:
        running.client.images.generate(model=task_model("video"), prompt="a cat")
    assert e.value.code == "model_not_supported"
    with pytest.raises(openai.NotFoundError) as e:
        running.client.images.generate(model="diffusers:no-such-model", prompt="a cat")
    assert e.value.code == "model_not_found"
    with pytest.raises(openai.BadRequestError) as e:
        running.client.images.generate(model=MODEL, prompt="a cat", response_format="url")
    assert e.value.param == "response_format"
