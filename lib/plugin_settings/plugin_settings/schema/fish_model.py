"""`providers.<p>.models.<m>` of a fish provider: one Fish Audio model that fish-speech runs."""

from __future__ import annotations

from pydantic import PositiveFloat, PositiveInt

from .voices import Voices

# GB Fish Audio Drama 3 took at its peak on one GPU (bf16, FP8 experts), measured with fish-speech.
DRAMA3_PEAK_GB = 44.0


class FishModel(Voices):
    """`repo`: the Hugging Face repository of a fish-speech checkpoint with its codec (`codec.pth`), or a local
    folder (an absolute or `~` path); `memory`: GB the model takes at its peak, checked against the free memory
    before the load; `style`: a format string with {instructions} and {text} (None: the model takes no
    instructions); `max_frames`: the audio frames one request generates at most, about 21.5 per second (None:
    fish-speech's default, 1024 per text chunk)."""

    repo: str
    memory: PositiveFloat = DRAMA3_PEAK_GB
    style: str | None = None
    max_frames: PositiveInt | None = None
