"""`MusicCreateParams`: the JSON body of `POST /v1/audio/music`, in the style of `openai.types.audio.SpeechCreateParams`
(the OpenAI API has no music endpoint)."""

from __future__ import annotations

from typing import Literal

from typing_extensions import Required, TypedDict


class MusicCreateParams(TypedDict, total=False):
    model: Required[str]
    """A local music model, `<provider>:<model>`."""

    prompt: Required[str]
    """The description of the track."""

    seconds: float
    """The length of the track; unset, the pipeline's own length."""

    lyrics: str
    """The lyrics; only a model with `lyrics_arg` takes them."""

    seed: int
    """The seed of the pipeline's generator."""

    response_format: Literal["wav"]
    """The audio format of the answer: a 16-bit WAV file at the pipeline's sample rate."""
