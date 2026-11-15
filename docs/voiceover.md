# voiceover

The voiceover skill turns a script of one sentence per line into `narration.wav` and `timing.json` with the start and
end of every sentence and word. Every model it uses is a model of `config.yaml`, run by `ai_models`
(`docs/ai_models.md`): the speech model (`--model`, else `models.speech`) and the align model (`models.align`).

## Speech models

`speech.Narrator` in `plugins/media/skills/voiceover/scripts/voiceover_tool/speech.py` calls `ai_models.speech.speak`
once per sentence. `ai_models.speech.check` refuses a speed or a style the model does not take when the narrator is
made, before any request or model load. The default voice is the provider's `voice`, else the kind's
(`ai_models.speech.TRAITS`). `voices` prints `ai_models.speech.voices` and, for a model whose kind clones a voice
(`chatterbox`, `vllm-omni`), the reference recordings of `add-voice` after them.

| kind | default voice | voices listed | style | speed |
|---|---|---|---|---|
| `kokoro` | `af_heart` | the voices of the prefixes in `langs` | refused | 0.5 to 2 |
| `chatterbox` | `default` | `default` and the recordings | refused | refused |
| `vllm-omni` | `default` | `default` and the recordings | through the provider's `style` | refused |
| `google` (Gemini TTS) | `Kore` | the default voice | text prefix | refused |
| `ollama` | `default` | the default voice | refused by the server | refused by the server |
| `openai`, `azure`, `openrouter` | `marin` | the default voice | `instructions` | 0.25 to 4 |

A provider's `voices` replaces the list. The voice of an API model is checked by the provider, not by the skill.
The answer is a WAV file, or raw 16-bit PCM taken as 24 kHz. Whether OpenRouter passes `instructions` on to Gemini TTS
is not verified.

A reference recording is a name in the voices directory (`VOICEOVER_VOICES_DIR`, default
`<media data dir>/voiceover/voices`) or a path; the skill passes its path to `ai_models`. A `vllm-omni` model also
needs its transcript, `<name>.txt` beside it (`add-voice --text`).

## Sentence times

Each sentence is synthesised on its own. The clip is trimmed at both ends of audio below -50 dBFS, keeping 30 ms, and
the clips are joined with fixed silences before the first sentence, between sentences and after the last. A sentence's
start and end are therefore known exactly from the clip lengths and the silences; no detection on the joined audio is
needed. The join assumes one sample rate: an answer at another rate (Drama 3: 44.1 kHz) is resampled to 24 kHz with
torchaudio's sinc interpolation.

## Word times

Word times come from forced alignment of each trimmed sentence clip against its known text with the align model of
`config.yaml` (`ai_models.align`; `torchaudio:MMS_FA` in the template) on the CPU. The aligner takes lowercase letters
and apostrophes only, so each written word is first mapped to aligner tokens (`normalize.py`, rules in its docstring,
among them `%` as "percent" and hyphenated words split into their parts).

When alignment of a sentence fails, its words are spread over the sentence in proportion to their character length and
the sentence is marked `"aligned": false`; a wrong word time is preferred to a failed run.

`timing.json` records `model` (the speech model id) and `style` when one is given. A script line that starts with
`[<style>]` is that sentence's style (`script.split_style`): the narrator passes it instead of `--style`, the
sentence in `timing.json` has the text without it and a `style` key, and `synth` checks every line style against the
model before the first request.

## Model options

Gemini TTS has no speed parameter, so the pace is asked for in the style. Chatterbox-Turbo has neither a speed nor a
style control; the delivery follows the reference recording. Ollama's speech API answers a speed other than 1 and
instructions with HTTP 400. Kokoro voices with the prefix `af_` or `am_` are phonemized as `en-us`, those with `bf_`
or `bm_` as `en-gb` (`langs` of the template), and any other Kokoro voice is refused. Ollama voice names are not
checked locally, since the server holds the list and answers an unknown voice with HTTP 400 naming the available ones.
Chatterbox runs on the CPU, which was faster than MPS on an Apple-silicon Mac.

## Dependency pins

The reasons not given in the comments of `scripts/pyproject.toml`:

- torch and torchaudio are pinned to 2.11, torchaudio's last release. It keeps `forced_align`, which the MMS_FA
  aligner uses, and flags it deprecated. torch follows torchaudio, which needs the matching torch version.
- `requires-python` is below 3.14; the skill is not tested on Python 3.14.
