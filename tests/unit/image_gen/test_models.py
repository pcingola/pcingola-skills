"""Image sizes within a model's image limits (`ImageLimits`, `providers.<p>.models.<m>.image`) for OpenAI-kind
and local models."""

import pytest

from image_gen_tool import models
from plugin_settings import ImageLimits

OPENAI = ImageLimits(max_edge=3840, min_pixels=655_360, max_pixels=8_294_400)
LOCAL = ImageLimits(max_edge=2048, min_edge=256)


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
    """1K square, 4K 16:9 and a 4K local square land on the documented sizes."""
    assert models.openai_size("1:1", "1K", OPENAI) == (1024, 1024)
    assert models.openai_size("16:9", "4K", OPENAI) == (3840, 2160)
    assert models.local_size("1:1", "4K", LOCAL) == (2048, 2048)


def test_openai_size_without_pixel_cap():
    """`max_pixels` None leaves the pixel count uncapped; `max_edge` still bounds the long edge."""
    assert models.openai_size("16:9", "4K", ImageLimits(max_edge=3840)) == (3840, 2160)
