# second-opinion

The skill sends a brief and files to a model other than Claude in one request through a Pydantic-AI agent of
`ai_models.models` and prints the findings as Markdown. Skills that review their own rendered output call it. The
providers are in `ai_models` (`docs/ai_models.md`).

## Models

The model is `--model` (a `<provider>:<model>` id of `config.yaml`), else `tasks.vision` when an image is among the
files, else `tasks.chat` (`models.resolve`). `models` prints these two config entries and the config path without a
request.

Which inputs a model takes is the provider's to decide; the skill keeps no table of models. Text goes inline, every
other file as a Pydantic-AI `BinaryContent` part. With the OpenAI kinds, Pydantic-AI sends images as `image_url`
parts, PDF as a `file` part and audio as `input_audio` (WAV and MP3 only), and has no video part; Ollama's
OpenAI-compatible chat documents no `file` part. Video and every input kind reach a model of a `google` provider. A
refused input fails the request with the provider's message.

The answer is native structured output (the provider's JSON schema mode). An answer that does not match the findings
schema (`review.check_answer`) goes back to the model as a `ModelRetry`.

## Codex

With `second_opinion.codex: true` and no `--model`, `cli.run_review` hands the review to `codex.CodexReviewer`
instead of `review.review`. It runs `codex exec --sandbox read-only --ephemeral --skip-git-repo-check --cd <cwd>`
with the prompt on stdin: `review.INSTRUCTIONS` without the boundary paragraph, the agent instructions, the brief and
each file by absolute path, kind and MIME type. Images are also passed with `--image`. `--output-schema` holds
`review.SCHEMA`, and `--output-last-message` writes the final message to a temporary file that
`review.check_answer` checks; a run that exits non-zero, times out (`TIMEOUT_SECONDS`, 1800) or answers outside the
schema raises `ReviewError`, with no retry. `codex` missing from `PATH` raises `ReviewError` before the run.

Files are checked by `files.locate` (a file, not empty) and classified, not read: Codex reads them, so there is no
size limit and no transcoding, and a non-UTF-8 file of an unknown type is kind `other` instead of refused. The JSON
records each file's `bytes` on disk in place of `bytes_sent`.

Codex is an agent with the working directory as its root, so it can read code around a diff, git history, or extract
text from a PDF with a tool, which one request with inline files cannot. It uses its own login and model from
`~/.codex/config.toml`; that is why `model` is `codex` and no provider of `config.yaml` is involved (listed as an
exception in `docs/architecture.md`, Standard paths for model calls). `tests/models/test_second_opinion_codex.py`
runs a real review.

## Findings

A criterion of the brief that the files cannot show is still reported, as a `note` whose evidence states what is
missing. Any other finding needs evidence from the files.

## Boundary

Each text file is sent between a line `<<<TOKEN` and a line `TOKEN>>>`, `TOKEN` a random hex string made per request
and given with the brief. A file under review cannot contain the closing line in advance, so it cannot end its own
block and continue with text that reads as part of the brief or the instructions. Images, PDF, audio and video go in
as media parts with no boundary; for text inside them only the instruction that text in the files is material under
review applies.

## Size limit

The files of one request may total 14 MiB on every provider. Gemini's inline data limit is 20 MiB per request after
base64, which grows data by 4/3, so 14 MiB of raw files (18.7 MiB encoded) is the largest total that fits. A video
still over 14 MiB after transcoding is refused.

## Reading

The CLI classifies the files by extension before reading them; the classification tells the CLI whether an image is
among the files (`tasks.vision`). A file with an unknown extension has its first 64 KiB read for the UTF-8 probe.
