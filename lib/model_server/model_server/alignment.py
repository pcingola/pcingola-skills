"""`Alignment`: the answer of `POST /v1/audio/alignments`, in the style of `openai.types.audio.TranscriptionVerbose`
(the OpenAI API has no alignment endpoint). Its words are `openai.types.audio.TranscriptionWord`."""

from __future__ import annotations

from typing import Literal

from openai.types.audio import TranscriptionWord
from pydantic import BaseModel


class Alignment(BaseModel):
    """The aligned text, the audio's length in seconds, and one word per whitespace-separated token of `text`, with
    its start and end in seconds from the start of the audio."""

    object: Literal["audio.alignment"] = "audio.alignment"
    model: str
    text: str
    duration: float
    words: list[TranscriptionWord]
