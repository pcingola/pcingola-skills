"""Image sizes within the limits of gpt-image-2 and of the local diffusers models."""

import pytest

from image_gen_tool import models


@pytest.mark.parametrize("aspect", models.ASPECT_RATIOS)
@pytest.mark.parametrize("size", models.IMAGE_SIZES)
def test_openai_size_within_limits(aspect, size):
    w, h = models.openai_size(aspect, size)
    assert (w % 16, h % 16) == (0, 0)
    assert max(w, h) <= 3840 and 655_360 <= w * h <= 8_294_400
    assert (w > h) == (models._ratio(aspect) > 1)


@pytest.mark.parametrize("aspect", models.ASPECT_RATIOS)
@pytest.mark.parametrize("size", models.IMAGE_SIZES)
def test_local_size_within_limits(aspect, size):
    w, h = models.local_size(aspect, size)
    assert (w % 16, h % 16) == (0, 0)
    assert 256 <= min(w, h) and max(w, h) <= 2048
    assert (w > h) == (models._ratio(aspect) > 1)


def test_reference_sizes():
    assert models.openai_size("1:1", "1K") == (1024, 1024)
    assert models.openai_size("16:9", "4K") == (3840, 2160)
    assert models.local_size("1:1", "4K") == (2048, 2048)
