"""`POST /v1/audio/speech`, `POST /v1/audio/music` and `POST /v1/audio/alignments` on local models.

Speech (`openai.types.audio.SpeechCreateParams`, JSON) runs `ai_models.speech.aspeak` on a fish, kokoro or chatterbox
model and answers the WAV file (`audio/wav`); `response_format` is `wav` (the default here), `speaker` (a field
outside the params type) names who speaks to a fish model, and `reference_audio` (another such field, base64 audio,
`References`) is the recording a cloning model (chatterbox) speaks in. Music (`MusicCreateParams`, JSON) runs
`ai_models.music.acompose` on a diffusers music model and answers a WAV file. Alignment (multipart: `model`, `file`,
`text`) runs the torchaudio aligner (`ai_models.align`) and answers `Alignment` (JSON).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from openai.types.audio import SpeechCreateParams, TranscriptionWord

from .alignment import Alignment
from .forms import checked, extras, one_file
from .model_role import ModelRole
from .music_create_params import MusicCreateParams
from .references import FIELD as REFERENCE
from .requests import json_body, server_of
from .server_error import ServerError

router = APIRouter()
WAV = "audio/wav"


def check_wav(body: dict[str, Any]) -> None:
    if body.get("response_format") not in (None, "wav"):
        raise ServerError(400, "local audio models answer wav only", param="response_format")
    if body.get("stream_format") not in (None, "audio"):
        raise ServerError(400, "local speech models do not stream", param="stream_format")


@router.post("/v1/audio/speech")
async def speech(request: Request) -> Response:
    from ai_models import speech as ai_speech

    body = checked(SpeechCreateParams, await json_body(request))
    srv = server_of(request)
    ref = srv.ref(body.get("model"), ModelRole.SPEECH)
    check_wav(body)
    more = extras(SpeechCreateParams, body, "speaker", REFERENCE)
    if more:
        raise ServerError(400, f"{ref.id} takes no request fields {', '.join(sorted(more))}", param=next(iter(more)))
    voice = body.get("voice")
    if isinstance(voice, dict):
        voice = voice.get("id")
    if REFERENCE in body:
        if not ai_speech.TRAITS[ref.kind].clones:
            raise ServerError(400, f"{ref.id} does not clone a voice; it takes no `{REFERENCE}`", param=REFERENCE)
        voice = str(srv.references.path(body[REFERENCE]))
    async with srv.running(ref):
        audio = await ai_speech.aspeak(body["input"], voice=voice or None, model=ref.id,
                                       instructions=body.get("instructions"), speed=float(body.get("speed") or 1.0),
                                       speaker=body.get("speaker"), weights_dir=srv.settings.weights_dir)
    return Response(audio, media_type=WAV)


@router.post("/v1/audio/music")
async def music(request: Request) -> Response:
    from ai_models import music as ai_music

    body = checked(MusicCreateParams, await json_body(request))
    srv = server_of(request)
    ref = srv.ref(body.get("model"), ModelRole.MUSIC)
    check_wav(body)
    if more := extras(MusicCreateParams, body):
        raise ServerError(400, f"{ref.id} takes no request fields {', '.join(sorted(more))}", param=next(iter(more)))
    async with srv.running(ref):
        tracks = await ai_music.acompose(body["prompt"], seconds=body.get("seconds"), lyrics=body.get("lyrics"),
                                         seed=body.get("seed"), model=ref.id)
    return Response(tracks[0].audio, media_type=WAV)


def align_audio(model_id: str, audio: bytes, text: str, weights_dir: Any) -> Alignment:
    """The `Alignment` of `audio` against the whitespace-separated tokens of `text`, by the aligner `model_id`."""
    from ai_models import align, local

    aligner = align.aligner(model_id, weights_dir)
    wave, rate = local.read_audio(audio, aligner.sample_rate, "mono")
    samples = wave[0].numpy()
    tokens = text.split()
    try:
        spans = aligner.align(samples, rate, tokens)
    except (KeyError, RuntimeError, ValueError) as e:
        raise ServerError(400, f"{model_id} cannot align the text: {type(e).__name__}: {e}; `text` is the aligner's "
                          "tokens (MMS_FA: lowercase letters and apostrophes) separated by spaces", param="text") from e
    words = [TranscriptionWord(word=t, start=s, end=e) for t, (s, e) in zip(tokens, spans)]
    return Alignment(model=model_id, text=text, duration=samples.shape[0] / rate, words=words)


@router.post("/v1/audio/alignments")
async def alignments(request: Request) -> JSONResponse:
    form = await request.form()
    srv = server_of(request)
    ref = srv.ref(form.get("model"), ModelRole.ALIGN)
    text = form.get("text")
    if not isinstance(text, str) or not text.split():
        raise ServerError(400, "the request has no `text` to align", param="text")
    audio = await one_file(form, "file", required=True)
    async with srv.running(ref):
        out = await asyncio.to_thread(align_audio, ref.id, audio, text, srv.settings.weights_dir)
    return JSONResponse(out.model_dump(mode="json"))
