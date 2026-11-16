"""Option checks and the lyria-002 request of `music` (no model call)."""

import pytest

from ai_models import AIModelsError, music


def test_check_options_per_kind():
    """Each kind of music model takes its own options; the others, seed with samples, more than 10 images
    and fewer than 1 sample are refused before any request."""
    music.check_options("stream", "g:lyria-3", seconds=30, lyrics="la", images=[(b"x", "image/png")])
    music.check_options("predict", "g:lyria-002", negative="drums", samples=2, seed=None, images=())
    music.check_options("diffusers", "local:ace", seconds=30, lyrics="la", seed=0)
    for api, options, message in [
        ("predict", {"images": [(b"x", "image/png")]}, "does not take images (images: stream)"),
        ("stream", {"negative": "drums", "seed": 1}, "does not take negative, seed"),
        ("diffusers", {"samples": 2}, "does not take samples"),
        ("predict", {"seed": 1, "samples": 2}, "mutually exclusive"),
        ("stream", {"images": [(b"x", "image/png")] * 11}, "at most 10 images"),
        ("predict", {"samples": 0}, "at least 1"),
    ]:
        with pytest.raises(AIModelsError, match=message.replace("(", r"\(").replace(")", r"\)")):
            music.check_options(api, "m", **options)


def test_predict_instance():
    """`negative_prompt`, `seed` and `sample_count` go in the instance, unset ones are left out."""
    assert music.predict_instance("piano", None, None, None) == {"prompt": "piano"}
    assert music.predict_instance("piano", "drums", 0, None) == {"prompt": "piano", "negative_prompt": "drums",
                                                                 "seed": 0}
    assert music.predict_instance("piano", None, None, 3) == {"prompt": "piano", "sample_count": 3}


def test_model_api_and_takes(tmp_path):
    """`music.model_api` names the API of a model by its provider (diffusers, predict for a model entry with
    `predict: true`, else stream) and `music.takes` its options; a provider kind without music models is a ConfigError. Run in a child
    process with its own config file."""
    from tests.settings_env import write_config
    from tests.subproc import child_env, py_value, run_python

    cfg = write_config(tmp_path / "config.yaml", providers={
        "g": {"kind": "google", "api_key": "k", "models": {"lyria-002": {"predict": True}}},
        "local": {"kind": "diffusers"}, "o": {"kind": "ollama"}})
    env = child_env(SKILLS_CONFIG=str(cfg))
    got = py_value("from ai_models import music",
                   "[[music.model_api(m), sorted(music.takes(m))] for m in ('local:x', 'g:lyria-002', 'g:lyria-3')]", env)
    assert got == [["diffusers", ["lyrics", "seconds", "seed"]], ["predict", ["negative", "samples", "seed"]],
                   ["stream", ["images", "lyrics", "seconds"]]]
    done = run_python("from ai_models import music\nmusic.model_api('o:m')", env)
    assert done.returncode != 0 and "has no music models" in done.stderr, done.stderr


def test_min_crest_db(tmp_path):
    """`music.min_crest_db` is the `min_crest_db` of a diffusers model entry, None for an entry without it and for a
    remote model; a value that is not a number fails at load with its YAML path."""
    from tests.settings_env import write_config
    from tests.subproc import child_env, py_value, run_python

    local = {"kind": "diffusers", "models": {"a": {"repo": "x/a", "min_crest_db": 13}, "b": {"repo": "x/b"}}}
    cfg = write_config(tmp_path / "config.yaml", providers={"g": {"kind": "google", "api_key": "k"}, "local": local})
    env = child_env(SKILLS_CONFIG=str(cfg))
    assert py_value("from ai_models import music",
                    "[music.min_crest_db(m) for m in ('local:a', 'local:b', 'g:lyria-3')]", env) == [13.0, None, None]
    local["models"]["c"] = {"repo": "x/c", "min_crest_db": "loud"}
    write_config(tmp_path / "config.yaml", providers={"local": local})
    done = run_python("from ai_models import music\nmusic.min_crest_db('local:a')", env)
    assert done.returncode != 0 and "providers.local.models.c.min_crest_db: Input should be a valid number" in \
        done.stderr, done.stderr
