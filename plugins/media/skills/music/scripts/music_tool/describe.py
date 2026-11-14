"""Description of a clip by a chat model that takes audio, through
`ai_models.models.agent`: `--model`, else the `audio` task's model of the
`ai_models` config. Without either, the model analysis is skipped with the
reason (`resolve_model`).

Two requests per clip, each with the clip inline, a fixed prompt and a
JSON output schema. The first (`DESCRIBE_PROMPT`, `DESCRIBE_SCHEMA`) contains
no brief, so the description is not primed by what was asked for. The
second (`VERDICT_PROMPT`, `VERDICT_SCHEMA`), sent only when a brief exists,
quotes that description and the briefs and asks for a verdict per brief.
Without any brief both verdicts are "no brief". An answer that lacks a key
the schema requires is asked again (`require_keys`).

WAV, MP3, FLAC and OGG files up to `INLINE_LIMIT_BYTES` are sent as they are
(the limit leaves room for base64 within the 20 MB inline request); larger
files and other formats (M4A and AAC are often MP4 containers) are first
transcoded by FFmpeg to a mono 128 kb/s MP3. Providers other than `google`
take WAV and MP3 only (`input_audio`), so FLAC and OGG are transcoded there.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ai_models import config as ai_config
from ai_models.errors import AIModelsError, explained
from ai_models.models import agent, kind

AUDIO_TASK = "audio"
# The formats OpenAI-compatible chat takes as `input_audio`.
OPENAI_AUDIO = ("audio/wav", "audio/mpeg")
# base64 grows the payload by 4/3; 14 MiB raw is 18.7 MiB encoded, under the 20 MiB inline limit
INLINE_LIMIT_BYTES = 14 * 1024 * 1024
MIME_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac", ".ogg": "audio/ogg"}
VERDICTS = ["fits", "partly", "does not fit", "no brief"]

DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "genre": {"type": "string"},
        "instruments": {"type": "array", "items": {"type": "string"}},
        "tempo_bpm": {"type": "number"},
        "mood": {"type": "string"},
        "energy": {"type": "string", "enum": ["low", "medium", "high"]},
        "energy_changes": {"type": "boolean"},
        "energy_change_description": {"type": "string"},
        "vocals": {"type": "boolean"},
        "vocals_description": {"type": "string"},
    },
}
DESCRIBE_SCHEMA["required"] = list(DESCRIBE_SCHEMA["properties"])

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "clip_brief_verdict": {"type": "string", "enum": VERDICTS},
        "clip_brief_reasons": {"type": "array", "items": {"type": "string"}},
        "style_brief_verdict": {"type": "string", "enum": VERDICTS},
        "style_brief_reasons": {"type": "array", "items": {"type": "string"}},
    },
}
VERDICT_SCHEMA["required"] = list(VERDICT_SCHEMA["properties"])

DESCRIBE_PROMPT = """You are listening to a music clip. Describe only what you hear.

Report:
- genre: the genre or style, a few words.
- instruments: the main instruments and sound sources you hear.
- tempo_bpm: your estimate of the tempo in beats per minute (0 if there is no perceptible beat).
- mood: the mood, a few words.
- energy: low, medium or high, overall.
- energy_changes: true if the energy changes noticeably over the clip; energy_change_description says how and when (for example "builds from sparse pads to full drums at 0:12"), or "steady".
- vocals: true if there is any singing, speech or vocal sample; vocals_description says what, or "none".
"""

VERDICT_PROMPT = """You are listening to a music clip. A listener described it, without knowing any brief, as:

{description}

Listen to the clip again and compare it with each brief below. Verdicts: "fits" (every requirement met), "partly" (some met, some not), "does not fit" (the main requirements are not met), or "no brief" when that brief is "(none)". Each reasons list names the requirements met and missed, citing what you hear and when; leave it empty for "no brief". Judge from the audio; a requirement you cannot hear is not met.

Clip brief (the prompt this clip was generated from):
{clip_brief}

Style brief (the style every clip should have):
{style_brief}
"""


class DescribeError(Exception):
    """The model description failed."""


def resolve_model(model: str | None = None) -> tuple[str | None, str | None]:
    """(model id, None) for `model`, else the `audio` task's model; (None, reason) when the config names
    none or the model's provider is not in it."""
    try:
        model_id = ai_config.resolve(model, AUDIO_TASK)
        kind(model_id)
    except AIModelsError as e:
        return None, str(e)
    return model_id, None


def audio_payload(path: Path, formats: tuple[str, ...] | None = None) -> tuple[bytes, str]:
    """The bytes and MIME type to send: the file itself, or an MP3 transcode
    when it is larger than INLINE_LIMIT_BYTES, of an unknown type, or of a
    type not in `formats` (MIME types; None: every type of MIME_TYPES)."""
    mime = MIME_TYPES.get(path.suffix.lower())
    if mime and formats is not None and mime not in formats:
        mime = None
    if mime and path.stat().st_size <= INLINE_LIMIT_BYTES:
        return path.read_bytes(), mime
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise DescribeError(f"{path.name} needs transcoding and ffmpeg is not on PATH")
    proc = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-c:a", "libmp3lame",
                           "-b:a", "128k", "-f", "mp3", "-"], capture_output=True)
    if proc.returncode != 0:
        raise DescribeError(f"ffmpeg could not transcode {path.name}: {proc.stderr.decode(errors='replace')[-300:]}")
    return proc.stdout, "audio/mpeg"


def verdict_prompt(description: dict, clip_brief: str | None, style_brief: str | None) -> str:
    return VERDICT_PROMPT.format(description=json.dumps(description, indent=1),
                                 clip_brief=(clip_brief or "").strip() or "(none)",
                                 style_brief=(style_brief or "").strip() or "(none)")


NO_VERDICT = {"clip_brief_verdict": "no brief", "clip_brief_reasons": [],
              "style_brief_verdict": "no brief", "style_brief_reasons": []}


def require_keys(schema: dict):
    """An output validator: the answer when it holds every key `schema` requires, else `ModelRetry`."""
    from pydantic_ai import ModelRetry

    def check(data: dict) -> dict:
        missing = [k for k in schema["required"] if k not in data]
        if missing:
            raise ModelRetry(f"the answer lacks {', '.join(missing)}")
        return data
    return check


def _ask(model: str, audio: bytes, mime: str, prompt: str, schema: dict) -> dict:
    from pydantic_ai import BinaryContent, StructuredDict

    a = agent(model, task=AUDIO_TASK, output_type=StructuredDict(schema, name="answer"))
    a.output_validator(require_keys(schema))
    with explained(model):
        return dict(a.run_sync([BinaryContent(data=audio, media_type=mime), prompt]).output)


def describe(model: str, path: Path, clip_brief: str | None, style_brief: str | None) -> dict:
    """The description (no brief in the request), then the verdicts when a
    brief exists."""
    audio, mime = audio_payload(path, None if kind(model) == "google" else OPENAI_AUDIO)
    try:
        description = _ask(model, audio, mime, DESCRIBE_PROMPT, DESCRIBE_SCHEMA)
        verdict = dict(NO_VERDICT)
        if (clip_brief or "").strip() or (style_brief or "").strip():
            verdict = _ask(model, audio, mime, verdict_prompt(description, clip_brief, style_brief), VERDICT_SCHEMA)
            # A brief that was not given has no verdict, whatever the model answered for it.
            for key, brief in (("clip_brief", clip_brief), ("style_brief", style_brief)):
                if not (brief or "").strip():
                    verdict[f"{key}_verdict"], verdict[f"{key}_reasons"] = "no brief", []
    except Exception as e:  # noqa: BLE001 - model errors are reported per clip
        raise DescribeError(f"{model}: {e}") from e
    return {"status": "ok", "model": model, "sent_mime_type": mime, **description, **verdict}


def skipped(reason: str) -> dict:
    return {"status": "skipped", "reason": reason}
