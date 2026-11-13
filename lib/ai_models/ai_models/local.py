"""Local images and music in process with `diffusers` (extra `ai-models[diffusers]`).

A model is `diffusers.<name>` in the config: `repo` (a Hugging Face repo, loaded
with `DiffusionPipeline.from_pretrained`; weights go to the Hugging Face cache),
`steps`, `guidance`, and `inpaint` (a diffusers pipeline class for mask edits,
built over the loaded modules with `from_pipe`). The device is CUDA, else MPS.
Pipelines stay loaded for the life of the process. torch and diffusers are
imported only here.
"""

from __future__ import annotations

import asyncio
import io
import wave
from typing import Any

from pydantic_ai.exceptions import UserError
from pydantic_ai.images import GeneratedImage, ImageGenerationModel, ImageGenerationResult
from pydantic_ai.messages import BinaryImage

from . import config
from .errors import AIModelsError, ConfigError

DEFAULT_MUSIC_SECONDS = 30.0
_pipes: dict[str, Any] = {}


def device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    raise AIModelsError(f"local models need a CUDA or Apple MPS GPU; torch {torch.__version__} sees neither")


def pipeline(repo: str, inpaint: str | None = None):
    """The loaded pipeline of `repo` in bfloat16, or the `inpaint` pipeline class over its modules."""
    import torch

    key = f"{repo}#{inpaint or ''}"
    if key not in _pipes:
        if inpaint:
            import diffusers

            # from_pipe casts the shared modules to float32 unless given the loaded dtype
            _pipes[key] = getattr(diffusers, inpaint).from_pipe(pipeline(repo), dtype=torch.bfloat16)
        else:
            from diffusers import DiffusionPipeline

            _pipes[key] = DiffusionPipeline.from_pretrained(repo, dtype=torch.bfloat16).to(device())
    return _pipes[key]


def pipe_kwargs(spec: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Steps and guidance of the model, then `extra`; `seed` becomes a torch generator."""
    kwargs = {k: v for k, v in (("num_inference_steps", spec.get("steps")),
                                ("guidance_scale", spec.get("guidance"))) if v is not None}
    kwargs.update(extra)
    if (seed := kwargs.pop("seed", None)) is not None:
        import torch

        dev = device()
        kwargs["generator"] = torch.Generator("cpu" if dev == "mps" else dev).manual_seed(int(seed))
    return kwargs


def repaint_mask(mask: bytes):
    """An OpenAI mask (transparent = edit) as a diffusers mask (white = repaint)."""
    from PIL import Image

    return Image.open(io.BytesIO(mask)).convert("RGBA").getchannel("A").point(lambda a: 255 if a == 0 else 0)


class DiffusersImageModel(ImageGenerationModel):
    """A Pydantic-AI image model on a local diffusers pipeline. Reference images go as
    `image`; with a `mask`, the first goes to the `inpaint` pipeline. `settings`:
    `dimensions` (width, height) and `extra_body` (more pipeline arguments, `seed`)."""

    def __init__(self, name: str, *, mask: bytes | None = None, settings=None) -> None:
        super().__init__(settings=settings)
        self._name = name
        self.spec = config.diffusers_model(name)
        self.mask = mask

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def system(self) -> str:
        return "diffusers"

    async def generate(self, prompt: str, *, images=None, settings=None) -> ImageGenerationResult:
        prompt, images, settings = self.prepare_generate(prompt, images=images, settings=settings)
        if any(not isinstance(i, BinaryImage) for i in images):
            raise UserError("local image models take reference images as BinaryImage")
        if self.mask is not None and not images:
            raise UserError("a mask needs a reference image to edit")
        if self.mask is not None and not self.spec.get("inpaint"):
            raise ConfigError(f"diffusers model {self._name!r} has no `inpaint` pipeline for a mask")
        return await asyncio.to_thread(self._run, prompt, [i.data for i in images], settings)

    def _run(self, prompt: str, refs: list[bytes], settings: dict[str, Any]) -> ImageGenerationResult:
        kwargs = pipe_kwargs(self.spec, dict(settings.get("extra_body") or {}))
        if dims := settings.get("dimensions"):
            kwargs["width"], kwargs["height"] = dims
        if refs:
            from PIL import Image
        pics = [Image.open(io.BytesIO(r)).convert("RGB") for r in refs]
        if self.mask is not None:
            kwargs.update(image=pics[0], mask_image=repaint_mask(self.mask))
            if len(pics) > 1:
                kwargs["image_reference"] = pics[1:]
        elif pics:
            kwargs["image"] = pics
        pipe = pipeline(self.spec["repo"], self.spec.get("inpaint") if self.mask is not None else None)
        out = []
        for img in pipe(prompt=prompt, **kwargs).images:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            out.append(GeneratedImage(BinaryImage(data=buf.getvalue(), media_type="image/png"), output_format="png"))
        return ImageGenerationResult(images=out, prompt=prompt, model_name=self._name, provider_name="diffusers")


class DiffusersMusicModel:
    """A local music pipeline (ACE-Step: `AceStepPipeline`)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.spec = config.diffusers_model(name)

    def compose(self, prompt: str, *, seconds: float | None = None, lyrics: str | None = None,
                seed: int | None = None) -> bytes:
        """A 16-bit WAV file of the track at the pipeline's sample rate."""
        import torch

        extra: dict[str, Any] = {"audio_duration": float(seconds or DEFAULT_MUSIC_SECONDS), "seed": seed}
        if lyrics is not None:
            extra["lyrics"] = lyrics
        pipe = pipeline(self.spec["repo"])
        audio = pipe(prompt=prompt, output_type="pt", **pipe_kwargs(self.spec, extra)).audios[0]  # (channels, samples)
        pcm = (audio.float().clamp(-1, 1) * 32767).to(torch.int16).T.contiguous().cpu().numpy().tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(audio.shape[0])
            w.setsampwidth(2)
            w.setframerate(int(pipe.sample_rate))
            w.writeframes(pcm)
        return buf.getvalue()
