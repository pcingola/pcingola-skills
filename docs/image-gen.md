# image-gen

Every request goes through `ai_models.images` (a Pydantic-AI `ImageGenerator`) on the provider of the model id. The
config, the provider kinds, the mask adapter and the local `diffusers` models are in `ai_models`
(`docs/ai_models.md`).

## Models

The model is `--model` (a `<provider>:<model>` id of `config.yaml`), else the model of the config task of `--tier`
(`models.task_for`):

| `--tier` | Task without `--ref` | Task with `--ref` |
|---|---|---|
| `fast` (default) | `image` | `image_edit` |
| `best` | `image_best` | `image_best` |
| `multi-ref` | `image_multi_ref` | `image_multi_ref` |

The tiers replace the aliases `fast`, `best` and `multi-ref` of the skill before the port, which mapped to a code
table of models per provider. A tier whose task the config lacks fails before any request with an `ImageError` naming
`models.<task>`. The skill has no model table and no model setting. The wrapper installs the
skill's `local` extra (`ai-models[diffusers]`) when the config has a provider of kind `diffusers`.

## Options per provider kind

`generate.settings` maps the CLI options to the Pydantic-AI settings of the model's provider kind:

| Kind | `--aspect`, `--size` | `--quality`, `--background`, output format | `--n` | mask |
|---|---|---|---|---|
| `openai`, `azure`, `openrouter`, `ollama` | `--size` gives `dimensions` from `models.openai_size` (edges of 16 px, at most 3840 px, 655,360 to 8,294,400 px); else `--aspect` goes as `aspect_ratio` | sent when given | one request with `openai_n` | yes |
| `google` | `google_image_config` with the aspect ratio and the size tier | PNG only, no transparent background | one request per image | no |
| `diffusers` | `dimensions` from `models.local_size` (edges of 16 px from 256 to 2048 px) | PNG only, no transparent background | one request per image | yes, with an `inpaint` pipeline |

A gpt-image model always gets `dimensions` (default 1:1, 1K) and quality `high` unless `--quality` is given, the
defaults the skill had before the port. Another model of an OpenAI kind gets no size or quality unless the user
gives one, so the model default applies. A `google` model always gets an aspect ratio and a size tier (default 1:1,
1K).

`--aspect` and `--size` default to None in the CLI, so a local edit without them sends no size and the pipeline keeps
the first reference image's size; a 1:1 default there would distort a 16:9 photo.

## Mask

`--mask` goes to `ai_models.images`. A `google` model refuses it with a `ConfigError` before any request. The model's
output is written unaltered: gpt-image-2 redraws the whole image and keeps the change mostly inside the mask, and
nothing is composited back, since pasting the original outside the mask leaves visible seams where the redraw
shifted colour or light.

## Errors

Every failure is an `ImageError` with one message for the CLI. A reference image that is not PNG, JPEG, WebP or GIF is
refused before any request. A moderation block (Pydantic-AI `ContentFilterError`) is reported as `Image generation
blocked` and not retried. HTTP 429 (`ModelRateLimitError`) is reported with a message telling the agent not to retry
and to ask the user to try again later, so an agent does not keep calling a rate-limited provider. A missing config
or key is the `ConfigError` message of `ai_models`.
