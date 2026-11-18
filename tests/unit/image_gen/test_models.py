"""Image sizes within a model's image limits (`OpenAIImageLimits`, `DiffusersImageLimits`, `providers.<p>.models.<m>.image`) for OpenAI-kind
and local models."""

import pytest

from image_gen_tool import models
from plugin_settings import DiffusersImageLimits, OpenAIImageLimits

OPENAI = OpenAIImageLimits(max_edge=3840, min_pixels=655_360, max_pixels=8_294_400)
LOCAL = DiffusersImageLimits(max_edge=2048, min_edge=256)


@pytest.mark.parametrize("aspect", models.ASPECT_RATIOS)
@pytest.mark.parametrize("size", models.IMAGE_SIZES)
def test_openai_size_within_limits(aspect, size):
    """openai_size keeps edges multiples of 16, the long edge within max_edge, the pixel count within
    min_pixels..max_pixels, and the orientation of the aspect."""
    w, h = models.openai_size(aspect, size, OPENAI)
    assert (w % 16, h % 16) == (0, 0)
    assert max(w, h) <= 3840 and 655_360 <= w * h <= 8_294_400
    assert (w > h) == (models._ratio(aspect) > 1)


@pytest.mark.parametrize("aspect", models.ASPECT_RATIOS)
@pytest.mark.parametrize("size", models.IMAGE_SIZES)
def test_local_size_within_limits(aspect, size):
    """local_size keeps edges multiples of 16 within min_edge..max_edge and the orientation of the aspect."""
    w, h = models.local_size(aspect, size, LOCAL)
    assert (w % 16, h % 16) == (0, 0)
    assert 256 <= min(w, h) and max(w, h) <= 2048
    assert (w > h) == (models._ratio(aspect) > 1)


def test_reference_sizes():
    """openai_size gives 1024x1024 for 1:1 1K and 3840x2160 for 16:9 4K; local_size gives 2048x2048 for 1:1 4K.
    Guards the --size table of image-gen's SKILL.md (3840 px long edge for gpt-image-2, 2048 px for local models)."""
    assert models.openai_size("1:1", "1K", OPENAI) == (1024, 1024)
    assert models.openai_size("16:9", "4K", OPENAI) == (3840, 2160)
    assert models.local_size("1:1", "4K", LOCAL) == (2048, 2048)


def test_openai_size_long_edge_bound():
    """openai_size keeps the long edge at `max_edge` (3840 for 16:9 4K) when `max_pixels` allows more pixels.
    Guards max_edge as a separate limit from the pixel count."""
    limits = OpenAIImageLimits(max_edge=3840, min_pixels=0, max_pixels=10**9)
    assert models.openai_size("16:9", "4K", limits) == (3840, 2160)
