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

`timing.json` records `model` (the speech model id), `style` when one is given, `speaker_voices` (each `@speaker`'s
voice; `default` for a made-up one) and `params` (the request fields of `--param`) when set. `Narrator.lines` reads
each line as the model takes it (`script.Line.of`):

- A model that takes inline tags (`Traits.tags`: vllm-omni): `@<name> ` at the start names the speaker; the rest
  goes to the model as written. The sentence aligned and written as `text` is the line without bracket tags and
  speaker tags (`strip_tags`); `said` holds the line as sent when it differs, `speaker` the speaker. A line of only
  tags is refused, and so is an `@` line whose name is not a speaker name (lowercase letters, digits, `-`, `_`).
  A speaker without `--speaker NAME=VOICE` is made up: its first take is the reference of its later lines
  (`omni.aspeak` keeps one take per speaker) and is written as `voice-<name>.wav` (`write_takes`); the made-up
  speakers are named on stderr. The narrator's `default` voice works the same way, and its first take is written as
  `voice.wav`. Each take has its transcript in the `.txt` of the same stem.
- A model that takes a style but no tags: a line that starts with `[<style>]` is that sentence's style
  (`split_style`), passed instead of `--style`, with a `style` key in `timing.json`. Such a model takes any style.
- Any other model: the line is literal text.

A line with what its model does not take, an `@speaker`, or a tag other than a leading style of a model that takes
styles, is refused, because the model would speak it. `--speaker` is refused for a model without tags, for a name
that is not a speaker name or that no line uses, and `--param` for a kind without request fields (`Traits.params`:
Kokoro, Chatterbox, Gemini). `Narrator.prepare` resolves every voice (the narrator's and each speaker's: a recording
of `add-voice` or a path, and for a vllm-omni model its transcript) before the aligner loads and before the first
request, so a missing recording or transcript fails before the minutes of a model start.

Local weights live in `voiceover/` of the plugin data directory (`config.weights_dir`) unless the provider sets `dir`;
voiceover passes it to `ai_models` as `weights_dir`. `setup --chatterbox` syncs the locked uv project
`scripts/chatterbox` (chatterbox-tts 0.1.7, which pins torch 2.6) into `voiceover-scripts-chatterbox/.venv` next to
voiceover's own environment under the plugin data directory (`config.chatterbox_env`, the `uv_env.sh` rule) and
prints its python, the `python` of the `chatterbox` provider. It needs the wrapper's `PLUGIN_ENV_DIR`.

`load_settings` refuses every `VOICEOVER_*` setting of the file other than `VOICEOVER_VOICES_DIR` (the model settings
of an earlier version), naming the template's provider entries and models that replace them; when
`VOICEOVER_MODEL_DIR` is among them, the message gives its value as the providers' `dir` and its `voices/` as
`VOICEOVER_VOICES_DIR`. It also refuses a routes.md row whose model is an earlier name (`kokoro`, `chatterbox`),
asking for a model id of a provider of that kind. A config error about a missing provider or model gets a hint that
the setup:settings template has the entries (`config.TEMPLATE_HINT`).

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
