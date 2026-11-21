"""Keep-alive, per-model unload, the local-model lock and the memory refusal of the model server
(docs/model_server.md, Keep-alive and Memory), each on a server of tests/config.yaml with one setting changed."""

import copy
import time

import openai
import pytest
import torch

from tests.integration.model_server.conftest import serve
from tests.prereq import requires
from tests.settings_env import config_sections, task_model, write_config

SPEECH = task_model("speech")
ALIGN = task_model("align")
WAIT_SECONDS = 6.0


def settings(tmp_path, keep_alive: float = 300, memory: dict[str, float] | None = None):
    """tests/config.yaml with `model_server.keep_alive` and the `memory` (GB) of the given model ids, written to
    `tmp_path`."""
    sections = copy.deepcopy(config_sections())
    sections["model_server"] = {"keep_alive": keep_alive}
    for model_id, gb in (memory or {}).items():
        provider, model = model_id.split(":", 1)
        sections["providers"][provider]["models"][model]["memory"] = gb
    return write_config(tmp_path / "config.yaml", **sections)


def wait_until(check, what: str) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not check():
        assert time.monotonic() < deadline, what
        time.sleep(0.1)


def test_keep_alive_unloads_an_idle_model(tmp_path):
    """A Kokoro model stays loaded after its request and unloads `keep_alive` seconds after it
    (`ai_models.local.unload_model`); its next request loads it again."""
    from ai_models import kokoro

    with serve(settings(tmp_path, keep_alive=1)) as r:
        r.client.audio.speech.create(model=SPEECH, input="Hello.", voice="af_heart", response_format="wav")
        assert SPEECH in r.server.residency.loaded and kokoro._models
        wait_until(lambda: SPEECH not in r.server.residency.loaded, "the model did not unload")
        assert not kokoro._models
        r.client.audio.speech.create(model=SPEECH, input="Again.", voice="af_heart", response_format="wav")
        assert kokoro._models


@requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
          f"local diffusers models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
def test_lock_held_while_a_gpu_model_is_loaded(tmp_path):
    """The server takes the local-model lock with its first diffusers load and keeps it while the model is loaded;
    `keep_alive` 0 unloads the model when its request ends and releases the lock."""
    from ai_models import local

    with serve(settings(tmp_path, keep_alive=0)) as r:
        r.client.images.generate(model=task_model("image"), prompt="a cat", size="128x128")
        assert not local._pipes and local._lock is None and not r.server.residency.loaded


def test_model_larger_than_the_device_is_refused(tmp_path):
    """A model whose `memory` exceeds the total memory is refused at once with HTTP 507 `insufficient_memory`, an
    OpenAI error body naming the GB, and the loaded models stay loaded."""
    from ai_models import align

    with serve(settings(tmp_path, memory={SPEECH: 100_000})) as r:
        r.http.post("/v1/audio/alignments", data={"model": ALIGN, "text": "hello"},
                    files={"file": ("a.wav", silence(), "audio/wav")})
        assert ALIGN in r.server.residency.loaded and align._aligners
        with pytest.raises(openai.APIStatusError) as e:
            r.client.audio.speech.create(model=SPEECH, input="Hello.", voice="af_heart", response_format="wav")
        assert (e.value.status_code, e.value.code) == (507, "insufficient_memory")
        assert "100000 GB" in e.value.message and "more than the" in e.value.message
        assert ALIGN in r.server.residency.loaded and align._aligners


@requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
          f"local diffusers models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
def test_gpu_model_without_memory_unloads_idle_gpu_models(tmp_path):
    """Before the first request of a GPU model without `memory`, the idle GPU models are unloaded: the image
    pipeline is gone once a video model ran, and the aligner (CPU) stays."""
    from ai_models import align, config, local
    from tests.integration.model_server.media import finished, png

    with serve(settings(tmp_path)) as r:
        image = config.local_entry(task_model("image")).repo
        r.client.images.generate(model=task_model("image"), prompt="a cat", size="128x128")
        r.http.post("/v1/audio/alignments", data={"model": ALIGN, "text": "hello"},
                    files={"file": ("a.wav", silence(), "audio/wav")})
        assert any(k.startswith(f"{image}#") for k in local._pipes)
        job = r.client.videos.create(model=task_model("video"), prompt="waves", seconds="0.3",
                                     input_reference=("still.png", png(64, 64), "image/png"))
        assert finished(r.client, job).status == "completed"
        assert not any(k.startswith(f"{image}#") for k in local._pipes)
        assert task_model("image") not in r.server.residency.loaded and align._aligners


def silence() -> bytes:
    """One second of 16 kHz mono 16-bit silence as a WAV file."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\0\0" * 16_000)
    return buf.getvalue()
