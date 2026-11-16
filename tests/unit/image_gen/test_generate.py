"""CLI options to Pydantic-AI image settings per provider kind, and the checks made before any model call."""

import contextlib
import io
import os
import subprocess
from pathlib import Path

import pytest

from image_gen_tool import cli
from image_gen_tool.generate import ImageError, media_type, settings
from image_gen_tool.models import task_for
from plugin_settings import ImageLimits
from tests.settings_env import write_config
from tests.subproc import child_env, run_python

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 24
# Image limits of an OpenAI-kind and a local model as config.example.yaml gives them, and of a sized model.
OPENAI_LIMITS = ImageLimits(max_edge=3840, min_pixels=655_360, max_pixels=8_294_400)
LOCAL_LIMITS = ImageLimits(max_edge=2048, min_edge=256)
SIZED_LIMITS = ImageLimits(max_edge=3840, min_pixels=655_360, max_pixels=8_294_400, always_sized=True,
                           default_quality="high")


def opts(kind, **kw):
    args = dict(aspect_ratio=None, image_size=None, n=1, quality=None, background=None, output_format="png",
                edit=False, limits=LOCAL_LIMITS if kind == "diffusers" else OPENAI_LIMITS)
    args.update(kw)
    return settings(kind, "p:m", **args)


def test_openai_kinds_one_request_with_n():
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
    """--size for a model without image limits fails with the config entry to add, for an OpenAI kind and a
    diffusers model. Runs in a child with its own config.yaml (ai_models.config.image_limits)."""
    cfg = write_config(tmp_path / "config.yaml", providers={"o": {"kind": "ollama"},
                                                            "local": {"kind": "diffusers",
                                                                      "models": {"m": {"repo": "x/m"}}}})
    code = ("from image_gen_tool.generate import settings, ImageError\n"
            "for kind, mid in (('ollama', 'o:img'), ('diffusers', 'local:m')):\n"
            "    try:\n"
            "        settings(kind, mid, aspect_ratio=None, image_size='2K', n=1, quality=None, background=None,\n"
            "                 output_format='png', edit=False, limits=None)\n"
            "    except ImageError as e:\n"
            "        print(e.message)\n")
    done = run_python(code, child_env(SKILLS_CONFIG=str(cfg)))
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert "add providers.o.models.img.image with max_edge" in lines[0], lines
    assert "add providers.local.models.m.image with max_edge (and min_edge)" in lines[1], lines


def test_google_one_request_per_image():
    assert opts("google", n=3, image_size="2K") == ({"google_image_config": {"image_size": "2K"}}, 3)


def test_google_leaves_missing_aspect_and_size_to_the_model():
    """Without --aspect and --size a Google model gets no image config, so an edit keeps the reference's
    aspect instead of becoming 1:1."""
    assert opts("google") == ({}, 1)
    assert opts("google", edit=True) == ({}, 1)
    assert opts("google", aspect_ratio="16:9")[0] == {"google_image_config": {"aspect_ratio": "16:9"}}


def test_diffusers_dimensions_and_edit_keeps_reference_size():
    assert opts("diffusers", n=2) == ({"dimensions": (1024, 1024)}, 2)
    assert opts("diffusers", edit=True) == ({}, 1)
    assert opts("diffusers", edit=True, aspect_ratio="16:9")[0]["dimensions"][0] > 1024


@pytest.mark.parametrize("kind", ["google", "diffusers"])
def test_png_only_kinds_refuse_other_formats(kind):
    with pytest.raises(ImageError, match="PNG only"):
        opts(kind, output_format="jpeg")
    with pytest.raises(ImageError, match="transparent"):
        opts(kind, background="transparent")


def test_media_type():
    assert media_type(PNG) == "image/png"
    assert media_type(b"\xff\xd8\xff\0") == "image/jpeg"
    assert media_type(b"RIFF\0\0\0\0WEBPVP8 ") == "image/webp"
    with pytest.raises(ImageError):
        media_type(b"not an image")


def run(*argv: str) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        try:
            cli.main(["generate", *argv])
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    return code, err.getvalue()


def test_cli_refusals_before_any_model_call(tmp_path):
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
        code, err = run(*argv)
        assert code != 0 and message in err, (argv, err)


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
    env = child_env(SKILLS_CONFIG=str(cfg))
    for tier, extra, key in (("best", [], "tasks.image_best"), ("multi-ref", ["--ref", str(ref)],
                                                                "tasks.image_multi_ref")):
        argv = ["generate", "--prompt", "a cat", "--out", out, "--tier", tier, *extra]
        done = run_python(f"from image_gen_tool import cli\ncli.main({argv!r})", env)
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
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and p.stdout == extra, p.stderr
