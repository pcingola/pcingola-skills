"""`ai_models.speech.speak` with a real vLLM-Omni speech model: the first model of the first provider of kind
`vllm-omni` in the user's config, served in its own environment (docs/ai_models.md, Speech models of vLLM-Omni). No small model exists for
Fish Audio Drama 3, so the test loads the full one (minutes)."""

import io
import wave
from pathlib import Path

from ai_models import config, omni, speech
from tests.prereq import requires


def _provider() -> str | None:
    try:
        providers = config.load().providers
    except config.ConfigError:
        return None
    return next((n for n, s in providers.items() if s.kind == omni.KIND), None)


NAME = _provider()
SPEC = config.provider(NAME) if NAME else None
MODEL = next(iter(SPEC.models), None) if SPEC else None
PYTHON = SPEC.python if SPEC else None
HAS_PYTHON = PYTHON is not None and Path(PYTHON).is_file()


@requires(NAME, f"no provider of kind {omni.KIND} in {config.path()} (see setup:settings, config.example.yaml)")
@requires(MODEL, f"provider {NAME!r} has no model in `models` (see setup:settings, config.example.yaml)")
@requires(HAS_PYTHON, f"the vLLM-Omni environment of provider {NAME!r} is missing: no `python` {PYTHON}")
def test_vllm_omni_speech_with_a_style_tag():
    """One sentence with a direction (the model's `style` format) comes back as a mono WAV of plausible length,
    and the server stops when asked."""
    data = speech.speak("The harbour lights come on one by one.", voice=omni.DEFAULT_VOICE,
                        model=f"{NAME}:{MODEL}", instructions="calm" if SPEC.models[MODEL].style else None)
    with wave.open(io.BytesIO(data)) as w:
        assert w.getnchannels() == 1
        assert 1.0 < w.getnframes() / w.getframerate() < 15
    srv = omni._servers[f"{NAME}:{MODEL}"]
    srv.stop()
    assert srv.proc.poll() is not None
