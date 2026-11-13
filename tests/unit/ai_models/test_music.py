"""Option checks and the lyria-002 request of `music` (no model call)."""

import pytest

from ai_models import AIModelsError, music


def test_check_options_per_kind():
    """Each kind of music model takes its own options; the others, seed with samples, more than 10 images
    and fewer than 1 sample are refused before any request."""
    music.check_options("stream", "g:lyria-3", seconds=30, lyrics="la", images=[(b"x", "image/png")])
    music.check_options("predict", "g:lyria-002", negative="drums", samples=2, seed=None, images=())
    music.check_options("diffusers", "local:ace", seconds=30, lyrics="la", seed=0)
    for api, options, message in [
        ("predict", {"images": [(b"x", "image/png")]}, "does not take images (images: stream)"),
        ("stream", {"negative": "drums", "seed": 1}, "does not take negative, seed"),
        ("diffusers", {"samples": 2}, "does not take samples"),
        ("predict", {"seed": 1, "samples": 2}, "mutually exclusive"),
        ("stream", {"images": [(b"x", "image/png")] * 11}, "at most 10 images"),
        ("predict", {"samples": 0}, "at least 1"),
    ]:
        with pytest.raises(AIModelsError, match=message.replace("(", r"\(").replace(")", r"\)")):
            music.check_options(api, "m", **options)


def test_predict_instance():
    """`negative_prompt`, `seed` and `sample_count` go in the instance, unset ones are left out."""
    assert music.predict_instance("piano", None, None, None) == {"prompt": "piano"}
    assert music.predict_instance("piano", "drums", 0, None) == {"prompt": "piano", "negative_prompt": "drums",
                                                                 "seed": 0}
    assert music.predict_instance("piano", None, None, 3) == {"prompt": "piano", "sample_count": 3}
