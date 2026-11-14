"""Image sizes within the size limits of the settings (`models.SizeLimits`) for OpenAI-kind and local models."""

import pytest

from image_gen_tool import models

LIMITS = models.SizeLimits(openai_max_edge=3840, openai_min_pixels=655_360, openai_max_pixels=8_294_400,
                           local_max_edge=2048, local_min_edge=256)


@pytest.mark.parametrize("aspect", models.ASPECT_RATIOS)
@pytest.mark.parametrize("size", models.IMAGE_SIZES)
def test_openai_size_within_limits(aspect, size):
    w, h = models.openai_size(aspect, size, LIMITS)
    assert (w % 16, h % 16) == (0, 0)
    assert max(w, h) <= 3840 and 655_360 <= w * h <= 8_294_400
    assert (w > h) == (models._ratio(aspect) > 1)


@pytest.mark.parametrize("aspect", models.ASPECT_RATIOS)
@pytest.mark.parametrize("size", models.IMAGE_SIZES)
def test_local_size_within_limits(aspect, size):
    w, h = models.local_size(aspect, size, LIMITS)
    assert (w % 16, h % 16) == (0, 0)
    assert 256 <= min(w, h) and max(w, h) <= 2048
    assert (w > h) == (models._ratio(aspect) > 1)


def test_reference_sizes():
    assert models.openai_size("1:1", "1K", LIMITS) == (1024, 1024)
    assert models.openai_size("16:9", "4K", LIMITS) == (3840, 2160)
    assert models.local_size("1:1", "4K", LIMITS) == (2048, 2048)
