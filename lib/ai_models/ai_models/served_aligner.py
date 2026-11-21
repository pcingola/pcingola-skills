"""`ServedAligner`: the forced aligner of a model server (`POST <base_url>/audio/alignments`), with the interface of
`align.Aligner`. The OpenAI API has no alignment call, so the request is a `client.post` of the `openai` SDK on the
Pydantic-AI provider's client, as speech is."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from .errors import AIModelsError


class ServedAligner:
    """The torchaudio aligner `model_id` of a model server (`served.require(model_id, Task.ALIGN)`). `align` sends
    the clip as a 16-bit WAV file at its own rate; the server resamples it to the aligner's rate."""

    def __init__(self, model_id: str, bare: str) -> None:
        self.model_id = model_id
        self.bare = bare

    def align(self, samples, rate: int, tokens: Sequence[str]) -> list[tuple[float, float]]:
        """One (start, end) in seconds from the start of `samples` (mono float at `rate` Hz) per token."""
        from .speech import float_wav

        return asyncio.run(self._align(float_wav(samples, rate), list(tokens)))

    async def _align(self, wav: bytes, tokens: list[str]) -> list[tuple[float, float]]:
        import httpx2
        from openai.types.audio import TranscriptionWord

        from . import served

        with served.answered(self.model_id):
            response = await served.client(self.model_id).post(
                "/audio/alignments", cast_to=httpx2.Response, body={"model": self.bare, "text": " ".join(tokens)},
                files=[("file", ("speech.wav", wav, "audio/wav"))],
                options={"headers": {"Content-Type": "multipart/form-data"}})
        words = [TranscriptionWord.model_validate(w) for w in response.json().get("words") or []]
        if len(words) != len(tokens):
            raise AIModelsError(f"{self.model_id}: the server aligned {len(words)} of {len(tokens)} tokens")
        return [(w.start, w.end) for w in words]
