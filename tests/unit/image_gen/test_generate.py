"""CLI options to Pydantic-AI image settings per provider kind, and the checks made before any model call."""

import os
import subprocess
from pathlib import Path

import pytest

from image_gen_tool import cli
from image_gen_tool.generate import ImageError, media_type, needs_size, request_limits, settings
from image_gen_tool.models import task_for
from plugin_settings import DiffusersImageLimits, OpenAIImageLimits
from tests.inproc import run_main
from tests.settings_env import use_settings, write_config

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 24
# Image limits of an OpenAI-kind and a local model as config.example.yaml gives them, and of a sized model.
OPENAI_LIMITS = OpenAIImageLimits(max_edge=3840, min_pixels=655_360, max_pixels=8_294_400)
LOCAL_LIMITS = DiffusersImageLimits(max_edge=2048, min_edge=256)
SIZED_LIMITS = OpenAIImageLimits(max_edge=3840, min_pixels=655_360, max_pixels=8_294_400, always_sized=True,
                           default_quality="high")


def opts(kind, **kw):
    """`settings` for a model of provider `kind` with the default options, overridden by `kw`."""
    args = dict(aspect_ratio=None, image_size=None, n=1, quality=None, background=None, output_format="png",
                edit=False, limits=LOCAL_LIMITS if kind == "diffusers" else OPENAI_LIMITS)
    args.update(kw)
    return settings(kind, "p:m", **args)


def test_openai_kinds_one_request_with_n():
    """OpenAI kinds make one request with `openai_n`; --size gives `dimensions`, else --aspect goes as
    `aspect_ratio`; quality, background and a non-PNG format go as their OpenAI settings."""
    assert opts("azure", n=3) == ({"openai_n": 3}, 1)
    s, calls = opts("openrouter", aspect_ratio="16:9", image_size="4K", n=2, quality="low",
                    background="transparent", output_format="webp")
    assert calls == 1
    assert s == {"openai_n": 2, "dimensions": (3840, 2160), "openai_quality": "low",
                 "openai_background": "transparent", "openai_output_format": "webp"}
    assert opts("openai", aspect_ratio="3:2")[0] == {"openai_n": 1, "aspect_ratio": "3:2"}


def test_sized_model_defaults_square_1k_and_default_quality():
    """A model whose image limits have `always_sized` gets 1:1 1K, and `default_quality` unless the options say
    otherwise; the choice follows the model's config entry, not its name (design: config_schema.md section 2)."""
    def gpt(**kw):
        args = dict(aspect_ratio=None, image_size=None, n=1, quality=None, background=None, output_format="png",
                    edit=False, limits=SIZED_LIMITS)
        return settings("azure", "azure:sized-model", **{**args, **kw})[0]

    assert gpt() == {"openai_n": 1, "dimensions": (1024, 1024), "openai_quality": "high"}
    assert gpt(aspect_ratio="16:9", quality="low")["openai_quality"] == "low"
    assert gpt(aspect_ratio="16:9")["dimensions"][0] > gpt(aspect_ratio="16:9")["dimensions"][1]


def test_openai_kind_without_limits_sends_no_size():
    """An OpenAI-kind model without image limits takes a request without --size (aspect as `aspect_ratio`), so
    a model with no config entry still serves plain requests."""
    assert opts("ollama", limits=None, aspect_ratio="3:2") == ({"openai_n": 1, "aspect_ratio": "3:2"}, 1)


def test_size_without_limits_names_config_entry(tmp_path):
    """--size for a model without image limits fails with the config entry to add and its required fields, for an
    OpenAI kind and a diffusers model; without a size, an OpenAI-kind model needs none. Reads its own config.yaml
    (ai_models.config.image_limits)."""
    cfg = write_config(tmp_path / "config.yaml", providers={"o": {"kind": "ollama"},
                                                            "local": {"kind": "diffusers",
                                                                      "models": {"m": {"repo": "x/m"}}}})
    with use_settings(cfg):
        assert request_limits("ollama", "o:img", aspect_ratio="3:2", image_size=None, edit=False) is None
        with pytest.raises(ImageError) as openai:
            request_limits("ollama", "o:img", aspect_ratio=None, image_size="2K", edit=False)
        with pytest.raises(ImageError) as local:
            request_limits("diffusers", "local:m", aspect_ratio=None, image_size="2K", edit=False)
    assert "add providers.o.models.img.image with max_edge, min_pixels, max_pixels" in openai.value.message
    assert "add providers.local.models.m.image with max_edge, min_edge" in local.value.message


def test_needs_size_per_kind():
    """An OpenAI kind needs a size only with --size; a diffusers model always, except an edit without --aspect
    and --size (the pipeline keeps the reference's size); google never."""
    def need(kind, **kw):
        return needs_size(kind, **{"aspect_ratio": None, "image_size": None, "edit": False, **kw})

    assert [need("azure"), need("azure", image_size="2K")] == [False, True]
    assert [need("diffusers"), need("diffusers", edit=True), need("diffusers", edit=True, aspect_ratio="1:1")] == \
        [True, False, True]
    assert need("google", image_size="2K") is False


def test_google_one_request_per_image():
    """A Google model gets one request per image, with --size in `google_image_config`."""
    assert opts("google", n=3, image_size="2K") == ({"google_image_config": {"image_size": "2K"}}, 3)


def test_google_leaves_missing_aspect_and_size_to_the_model():
    """Without --aspect and --size a Google model gets no image config, so an edit keeps the reference's
    aspect instead of becoming 1:1."""
    assert opts("google") == ({}, 1)
    assert opts("google", edit=True) == ({}, 1)
    assert opts("google", aspect_ratio="16:9")[0] == {"google_image_config": {"aspect_ratio": "16:9"}}


def test_diffusers_dimensions_and_edit_keeps_reference_size():
    """A diffusers model gets `dimensions` (1:1 1K by default) and one request per image; an edit without --aspect
    and --size gets none, so the pipeline keeps the reference's size; an edit with --aspect gets them."""
    assert opts("diffusers", n=2) == ({"dimensions": (1024, 1024)}, 2)
    assert opts("diffusers", edit=True) == ({}, 1)
    assert opts("diffusers", edit=True, aspect_ratio="16:9")[0]["dimensions"][0] > 1024


@pytest.mark.parametrize("kind", ["google", "diffusers"])
def test_png_only_kinds_refuse_other_formats(kind):
    """Google and diffusers models refuse a non-PNG output and a transparent background with an `ImageError`."""
    with pytest.raises(ImageError, match="PNG only"):
        opts(kind, output_format="jpeg")
    with pytest.raises(ImageError, match="transparent"):
        opts(kind, background="transparent")


def test_media_type():
    """A reference image's media type comes from its leading bytes (PNG, JPEG, WebP); other bytes are an
    `ImageError`."""
    assert media_type(PNG) == "image/png"
    assert media_type(b"\xff\xd8\xff\0") == "image/jpeg"
    assert media_type(b"RIFF\0\0\0\0WEBPVP8 ") == "image/webp"
    with pytest.raises(ImageError):
        media_type(b"not an image")


def test_cli_refusals_before_any_model_call(tmp_path):
    """`generate` refuses, before any model call, an unsupported output extension, a mask without a reference,
    --n 0, an empty prompt, a reference that is not an image and a missing reference: exit 1, `Error: <reason>` on
    stderr, nothing on stdout."""
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG)
    bad = tmp_path / "ref.txt"
    bad.write_bytes(b"text")
    out = str(tmp_path / "o.png")
    cases = [
        (["--prompt", "a cat", "--out", str(tmp_path / "o.gif")], "Unsupported output extension"),
        (["--prompt", "a cat", "--out", out, "--mask", str(ref)], "--mask needs a --ref"),
        (["--prompt", "a cat", "--out", out, "--n", "0"], "--n must be at least 1"),
        (["--prompt", " ", "--out", out], "Prompt cannot be empty"),
        (["--prompt", "a cat", "--out", out, "--ref", str(bad)], "not a PNG"),
        (["--prompt", "a cat", "--out", out, "--ref", str(tmp_path / "missing.png")], "not found"),
    ]
    for argv, message in cases:
        done = run_main(cli.main, "generate", *argv)
        assert done.returncode == 1 and done.stderr.startswith("Error: ") and message in done.stderr, (argv, done)
        assert done.stdout == "", (argv, done)


def test_tier_tasks():
    """Tier fast takes image, or image_edit for an edit; best and multi-ref take their own task either way.
    Guards the tier-to-task table that replaced the old aliases."""
    assert [task_for("fast", False), task_for("fast", True)] == ["image", "image_edit"]
    assert [task_for("best", False), task_for("best", True)] == ["image_best", "image_best"]
    assert [task_for("multi-ref", False), task_for("multi-ref", True)] == ["image_multi_ref", "image_multi_ref"]


def test_cli_tier_without_task_names_config_key(tmp_path):
    """A tier whose task the config lacks fails before any model call with a message naming tasks.<task>."""
    cfg = write_config(tmp_path / "config.yaml", providers={"o": {"kind": "ollama"}},
                       tasks={"image": "o:img", "image_edit": "o:edit"})
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG)
    out = str(tmp_path / "o.png")
    for tier, extra, key in (("best", [], "tasks.image_best"), ("multi-ref", ["--ref", str(ref)],
                                                                "tasks.image_multi_ref")):
        done = run_main(cli.main, "generate", "--prompt", "a cat", "--out", out, "--tier", tier, *extra,
                        settings=cfg)
        assert done.returncode != 0 and key in done.stderr and f"--tier {tier}" in done.stderr, done.stderr


@pytest.mark.parametrize("text, extra", [("providers:\n  local: {kind: diffusers}\n", "--extra local"),
                                         ("providers:\n  local:\n    kind: diffusers\n", "--extra local"),
                                         ("providers:\n  o: {kind: ollama}\n", "")])
def test_wrapper_local_extra(tmp_path, text, extra):
    """The wrapper adds `--extra local` to `uv run` exactly when the config of SKILLS_CONFIG has a
    provider of kind diffusers, in flow and block style. Runs the wrapper's own lines in bash."""
    scripts = Path(__file__).resolve().parents[3] / "plugins/media/skills/image-gen/scripts"
    config = tmp_path / "config.yaml"
    config.write_text(text)
    wrapper = (scripts / "image-gen.sh").read_text().splitlines()
    start = next(i for i, line in enumerate(wrapper) if line.startswith("CONFIG="))
    end = next(i for i, line in enumerate(wrapper) if line.startswith("exec "))
    script = "\n".join([f"source {scripts.parents[2] / 'lib/uv_env.sh'}", *wrapper[start:end], 'printf %s "$EXTRA"'])
    p = subprocess.run(["bash", "-euc", script], env={"PATH": os.environ["PATH"], "HOME": str(tmp_path),
                                                     "SKILLS_CONFIG": str(config)},
                       capture_output=True, text=True, timeout=25)
    assert p.returncode == 0 and p.stdout == extra, p.stderr
