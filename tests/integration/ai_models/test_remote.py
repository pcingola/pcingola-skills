"""Real calls to Azure OpenAI, Vertex AI and OpenRouter, with the providers of the user's `config.yaml`
(`azure`, `vertex`, `openrouter`, as in the config.example.yaml of setup:settings); a test fails when its
provider or key is missing."""

import io
import wave

import pytest
from pydantic_ai.messages import BinaryImage

from ai_models import config, images, models, music, speech
from ai_models.errors import ConfigError


def require_provider(name: str) -> None:
    """Fail the test unless the user's config.yaml has provider `name` with its `api_key`."""
    config.use(None)
    try:
        if config.provider(name).key() is None:
            pytest.fail(f"provider {name!r} of the user's config.yaml has no api_key")
    except ConfigError as e:
        pytest.fail(f"provider {name!r} of the user's config.yaml: {e}")


def _png(width: int = 64, height: int = 64, alpha: int = 255) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (width, height), (255, 255, 255, alpha)).save(buf, format="PNG")
    return buf.getvalue()


def test_openrouter_chat():
    require_provider("openrouter")
    result = models.agent("openrouter:google/gemini-2.5-flash-lite").run_sync("Reply with the word OK.")
    assert result.output.strip()


def test_openrouter_image():
    """The cheapest OpenRouter image model, at low quality."""
    require_provider("openrouter")
    gen = images.image_generator("openrouter:openai/gpt-5-image-mini")
    result = gen.generate_sync("a red circle on white", settings={"openai_quality": "low"})
    assert result.image.media_type.startswith("image/")


def test_vertex_chat():
    require_provider("vertex")
    assert models.agent("vertex:gemini-3.1-pro-preview").run_sync("Reply with the word OK.").output.strip()


def test_azure_speech():
    require_provider("azure")
    audio = speech.speak("Hello.", voice="alloy", model="azure:gpt-4o-mini-tts")
    assert audio[:4] == b"RIFF"


def test_vertex_gemini_speech():
    require_provider("vertex")
    audio = speech.speak("Hello.", voice="Kore", model="vertex:gemini-3.8-flash-tts")
    with wave.open(io.BytesIO(audio)) as w:
        assert w.getnframes() > 0


def test_vertex_lyria_002():
    require_provider("vertex")
    assert music.compose("calm solo piano", model="vertex:lyria-002")[0].audio[:4] == b"RIFF"


def test_azure_image_edit_with_mask():
    require_provider("azure")
    ref = BinaryImage(data=_png(1024, 1024), media_type="image/png")
    gen = images.image_generator("azure:gpt-image-2", mask=_png(1024, 1024, alpha=0))
    result = gen.generate_sync("a red circle", images=[ref], settings={"openai_quality": "low"})
    assert result.image.media_type.startswith("image/")
