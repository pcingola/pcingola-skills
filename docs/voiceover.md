# voiceover

The voiceover skill turns a script of one sentence per line into `narration.wav` and `timing.json` with the start and
end of every sentence and word. The `speech` backend's requests go through `ai_models` (`docs/ai_models.md`).

## Backends

`kokoro` (the default) and `chatterbox` run in the process and need no provider. They are not part of `ai_models`.
`speech` (`speech.SpeechBackend`) calls `ai_models.speech.speak` with the `speech` model of `config.yaml`, one request
per sentence; the skill has no model setting and no model flag. The provider kind of that model sets the rest:

| kind | default voice | voices listed | style | speed |
|---|---|---|---|---|
| `google` (Gemini TTS) | `Kore` | 30 Gemini voices | text prefix | no |
| `ollama` | `default` | 5 Ollama voices | refused by the server | refused by the server |
| `openai`, `azure`, `openrouter` | `marin` | 13 OpenAI voices | `instructions` | 0.25 to 4 |

The voice is checked by the provider, not by the skill; `voices --backend speech` lists the documented voices of the
kind. The answer is a WAV file, or raw 16-bit PCM taken as 24 kHz. Whether OpenRouter passes `instructions` on to
Gemini TTS is not verified.

## Sentence times

Each sentence is synthesised on its own. The clip is trimmed at both ends of audio below -50 dBFS, keeping 30 ms, and
the clips are joined with fixed silences before the first sentence, between sentences and after the last. A sentence's
start and end are therefore known exactly from the clip lengths and the silences; no detection on the joined audio is
needed. The join assumes one sample rate: the kokoro and speech backends refuse an answer that is not 24 kHz, and
Chatterbox-Turbo's output is fixed at 24 kHz.

## Word times

Word times come from forced alignment of each trimmed sentence clip against its known text with torchaudio's MMS_FA
model on the CPU. The aligner takes lowercase letters and apostrophes only, so each written word is first mapped to
aligner tokens (`normalize.py`, rules in its docstring, among them `%` as "percent" and hyphenated words split into
their parts).

When alignment of a sentence fails, its words are spread over the sentence in proportion to their character length and
the sentence is marked `"aligned": false`; a wrong word time is preferred to a failed run.

`timing.json` records `model` for every backend except kokoro, and `style` when one is given.

## Backend options

Kokoro has no style input. Gemini TTS has no speed parameter, so the pace is asked for in the style. Chatterbox-Turbo
has neither a speed nor a style control; the delivery follows the reference recording. Ollama's speech API answers a
speed other than 1 and instructions with HTTP 400. The speech backend refuses a speed outside 0.25 to 4, and any speed
other than 1 for a `google` model. A style is refused when the backend is made and a speed on the first sentence, both
before any request or model load.

Kokoro voices with the prefix `af_` or `am_` are phonemized as `en-us`, those with `bf_` or `bm_` as `en-gb`, and any
other Kokoro voice is refused. Ollama voice names are not checked locally, since the server holds the list and answers
an unknown voice with HTTP 400 naming the available ones. Chatterbox runs on the CPU, which was faster than MPS on an
Apple-silicon Mac.

## Dependency pins

The reasons not given in the comments of `scripts/pyproject.toml`:

- torch and torchaudio are pinned to 2.11, torchaudio's last release. It keeps `forced_align`, which the MMS_FA
  aligner uses, and flags it deprecated. torch follows torchaudio, which needs the matching torch version.
- `requires-python` is below 3.14; the skill is not tested on Python 3.14.
- chatterbox-tts 0.1.7 pins torch and torchaudio 2.6 below Python 3.14 and numpy<2 below Python 3.13; the overrides
  replace both pins.
- Under numpy 2, Chatterbox's `norm_loudness` multiplies the float32 reference by a float64 gain and returns float64
  (NEP 50 promotion), which its mel filter matmul rejects. The backend wraps it to cast the result to float32.
- `HF_HUB_OFFLINE=1` is set before Chatterbox is imported, unless already set, so that loading the local weights makes
  no request to huggingface.co.

## Weights

Kokoro comes from the kokoro-onnx GitHub release,
MMS_FA from Meta's download server (`dl.fbaipublicfiles.com`), and Chatterbox-Turbo from the ModelScope mirror of
Resemble AI's repository (`www.modelscope.cn/models/ResembleAI/chatterbox-turbo`). One downloader fetches all of them,
MMS_FA included instead of torch.hub's, so every download checks its size and none is left half-written under its
final name. The downloads use httpx's default TLS context, which honours `SSL_CERT_FILE`.

## espeak-ng path length

espeak-ng, which kokoro-onnx phonemizes with, keeps its data path in a 160-byte buffer and fails on a longer one. When
the bundled `espeak-ng-data` path is 150 characters or longer, `espeak.py` passes kokoro-onnx a copy at a short path.
