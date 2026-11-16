"""GPU-free cases of the diffusers models: mask conversion, argument order and config errors raised before any
pipeline loads. The cases that load a pipeline are in tests/integration/ai_models/test_local.py."""

import io

import pytest
from PIL import Image
from pydantic_ai.exceptions import UserError
from pydantic_ai.images import ImageGenerator
from pydantic_ai.messages import BinaryImage

from ai_models import ConfigError, local
from plugin_settings import DiffusersModel

NO_REPO = "no/such-repo"  # these cases fail before a pipeline loads


@pytest.fixture(autouse=True)
def _config(write_config):
    write_config({"providers": {"local": {"kind": "diffusers", "models": {
        "inpainter": {"repo": NO_REPO, "steps": 2, "guidance": 1.0, "inpaint": "Flux2KleinInpaintPipeline"},
        "no-inpaint": {"repo": NO_REPO, "steps": 2},
        "m": {"repo": NO_REPO, "steps": 1},
    }}}})


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_repaint_mask_is_white_where_transparent():
    """An OpenAI mask (transparent = edit) becomes a diffusers mask, white where the image is repainted."""
    mask = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    mask.putpixel((0, 0), (0, 0, 0, 0))
    m = local.repaint_mask(png(mask))
    assert [m.getpixel((0, 0)), m.getpixel((1, 0))] == [255, 0]


def test_mask_needs_a_reference_and_an_inpaint_pipeline():
    """A mask edit needs a reference image, and a model entry with an `inpaint` pipeline; both are checked before
    any pipeline loads."""
    with pytest.raises(UserError, match="reference image"):
        ImageGenerator(local.DiffusersImageModel("local:inpainter", mask=b"m")).generate_sync("x")
    ref = BinaryImage(data=b"\x89PNG", media_type="image/png")
    with pytest.raises(ConfigError, match="inpaint"):
        ImageGenerator(local.DiffusersImageModel("local:no-inpaint", mask=b"m")).generate_sync("x", images=[ref])


def test_pipe_kwargs_order_and_optional_guidance():
    """A model entry's steps, guidance (only when set) and `args` go to the pipeline call, and the caller's arguments
    override `args` (docs/ai_models.md, `diffusers`). Guards a pipeline without `guidance_scale` and the model's
    fixed call arguments."""
    spec = DiffusersModel(repo="r", steps=4, args={"true_cfg_scale": 4.0, "max_sequence_length": 256})
    assert local.pipe_kwargs(spec, {"max_sequence_length": 512}) == {
        "num_inference_steps": 4, "true_cfg_scale": 4.0, "max_sequence_length": 512}
    assert "guidance_scale" in local.pipe_kwargs(DiffusersModel(repo="r", steps=1, guidance=1.0), {})


def test_music_option_needs_its_argument_name():
    """A local music model takes `seconds` and `lyrics` only when its entry names their pipeline arguments
    (`duration_arg`, `lyrics_arg`); without one the option is a ConfigError before any pipeline loads. Guards a
    diffusers music pipeline with other argument names."""
    with pytest.raises(ConfigError, match="duration_arg"):
        local.DiffusersMusicModel("local:m").compose("piano", seconds=10)
    with pytest.raises(ConfigError, match="lyrics_arg"):
        local.DiffusersMusicModel("local:m").compose("piano", lyrics="la")


def _wav(rate: int, channels: int, seconds: float) -> bytes:
    import wave

    import numpy as np

    n = int(rate * seconds)
    tone = (np.sin(np.arange(n) * 2 * np.pi * 440 / rate) * 16000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.repeat(tone, channels).tobytes())
    return buf.getvalue()


def test_read_audio_keeps_or_resamples():
    """read_audio decodes a WAV at its own rate and channels, or resampled and mixed to mono at a given rate (the
    presenter model's input), as float32 (channels, samples) in [-1, 1]."""
    data = _wav(24000, 2, 0.5)
    track, rate = local.read_audio(data)
    assert rate == 24000 and track.shape[0] == 2 and abs(track.shape[1] - 12000) <= 32
    mono, rate = local.read_audio(data, 16000, "mono")
    assert rate == 16000 and mono.shape[0] == 1 and abs(mono.shape[1] - 8000) <= 32
    assert str(mono.dtype) == "torch.float32" and float(mono.abs().max()) <= 1.0


def test_waveform_takes_one_or_two_dimensions():
    """waveform makes a pipeline's audio (channels, samples): a 1-D array (Kandinsky 6 returns (samples,) per
    video, as NumPy with output_type np) gets a channel axis; a 2-D tensor (LTX-2) stays."""
    import numpy as np
    import torch

    assert tuple(local.waveform(np.zeros(100, dtype=np.float32)).shape) == (1, 100)
    assert tuple(local.waveform(torch.zeros(2, 100, dtype=torch.bfloat16)).shape) == (2, 100)


S2V_BUCKETS = [[512, 512], [512, 768], [768, 512]]


def test_presenter_still_follows_the_portrait_and_keeps_the_top():
    """A 2:3 portrait with no aspect (a presenter scene in a 16:9 film) takes the 512x768 bucket, not 768x512, and
    a crop to a square bucket keeps more of the top than the bottom (`PRESENTER_CENTERING`). Guards the head cut
    off by a centred crop to the film's aspect."""
    img = Image.new("RGB", (400, 600), (0, 0, 255))
    assert local.presenter_still(S2V_BUCKETS, png(img)).size == (512, 768)
    for y in range(600):  # row y is red y * 255 / 599, so the crop's top row tells how much of the top it keeps
        for x in range(400):
            img.putpixel((x, y), (round(y * 255 / 599), 0, 0))
    square = local.presenter_still(S2V_BUCKETS, png(img), 1.0)
    assert square.size == (512, 512)
    top, bottom = square.getpixel((256, 0))[0], 255 - square.getpixel((256, 511))[0]
    assert top < bottom
