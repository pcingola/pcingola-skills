"""Local images and music in process with `diffusers` (extra `ai-models[diffusers]`), and the
pipeline cache and device of every local model (video: `video`).

A model is `diffusers.<name>` in the config: `repo` (a Hugging Face repo, loaded
with `DiffusionPipeline.from_pretrained`; weights go to the Hugging Face cache),
`steps`, `guidance`, and `inpaint` (a diffusers pipeline class for mask edits,
built over the loaded modules with `from_pipe`). A video model also has
`pipeline` (the class to load), `fps`, `size_multiple`, `frame_step`, `width`, `height` and
`max_frames` (see `video`). The device is CUDA, else MPS.
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

_pipes: dict[str, Any] = {}


def device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    raise AIModelsError(f"local models need a CUDA or Apple MPS GPU; torch {torch.__version__} sees neither")


def pipeline(repo: str, inpaint: str | None = None, *, cls: str = "DiffusionPipeline"):
    """The loaded pipeline of `repo` in bfloat16, or the `inpaint` pipeline class over its modules.
    `cls` is the diffusers class to load."""
    import diffusers
    import torch

    key = f"{repo}#{inpaint or ''}#{cls}"
    if key not in _pipes:
        if inpaint:
            # from_pipe casts the shared modules to float32 unless given the loaded dtype
            _pipes[key] = getattr(diffusers, inpaint).from_pipe(pipeline(repo), dtype=torch.bfloat16)
        else:
            _pipes[key] = getattr(diffusers, cls).from_pretrained(repo, dtype=torch.bfloat16).to(device())
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
    """A local music pipeline: `prompt`, `lyrics` and `audio_duration` in, `.audios` and `sample_rate` out."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.spec = config.diffusers_model(name)

    def compose(self, prompt: str, *, seconds: float | None = None, lyrics: str | None = None,
                seed: int | None = None) -> bytes:
        """A 16-bit WAV file of the track at the pipeline's sample rate; without `seconds`, the pipeline's own length."""
        import torch

        extra: dict[str, Any] = {"seed": seed}
        if seconds is not None:
            extra["audio_duration"] = float(seconds)
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


def animate(name: str, image: bytes, prompt: str, *, seconds: float, width: int | None = None,
            height: int | None = None, seed: int | None = None) -> bytes:
    """An MP4 (H.264, no audio) of the image-to-video model `diffusers.<name>`. The image is cropped to
    the clip's aspect ratio and scaled to its size. An audio track the pipeline generates is dropped."""
    import tempfile
    from pathlib import Path

    from diffusers.utils import export_to_video
    from PIL import Image, ImageOps

    from .video import frame_count, frame_size, video_spec

    spec = video_spec(name)
    w, h = frame_size(width or spec["width"], height or spec["height"], spec["size_multiple"])
    frames_n = frame_count(seconds, spec["fps"], spec["frame_step"], spec["max_frames"])
    extra: dict[str, Any] = {"width": w, "height": h, "num_frames": frames_n, "seed": seed}
    pipe = pipeline(spec["repo"], cls=spec["pipeline"])
    still = ImageOps.fit(Image.open(io.BytesIO(image)).convert("RGB"), (w, h))
    frames = pipe(image=still, prompt=prompt, output_type="np", **pipe_kwargs(spec, extra)).frames[0]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp4"
        export_to_video(list(frames), str(out), fps=spec["fps"])
        return out.read_bytes()
