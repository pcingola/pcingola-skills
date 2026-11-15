---
name: voiceover
description: "Generates narration audio from a script with sentence and word timings (Kokoro, Chatterbox voice cloning, or the configured speech model). TRIGGER when: user asks for a voiceover, narration, TTS, a cloned voice, 'in my voice', or word timings."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/voiceover.sh:*) Read Skill
metadata:
  version: "0.1.0"
---

# Voiceover

Turns a script into `narration.wav` plus `timing.json` with the start and end
of every sentence and every word. A TTS backend synthesises each sentence, and
torchaudio's MMS_FA aligner (local, CPU) force-aligns each sentence against
its known text to get word times.

| backend | runs | default voice | speed | style |
|---|---|---|---|---|
| `kokoro` (default) | local CPU, `kokoro-onnx` | `af_heart` | yes | no |
| `chatterbox` | local CPU, Chatterbox-Turbo | `default` | no | no |
| `speech` | the `speech` model of the `ai_models` config | `Kore` (Gemini TTS), `default` (Ollama, vllm-omni), else `marin` | yes, OpenAI-style models (0.25 to 4); not Gemini TTS or vllm-omni | yes |

Use `kokoro` unless the user asks for another backend. The `speech` backend
sends each sentence to the model that the settings file `config.yaml` names
for the `speech` task: an
OpenAI-style `audio/speech` model (OpenAI, Azure, OpenRouter, Ollama) or a
Gemini TTS model. The provider checks the voice; `voices --backend speech`
lists the documented voices for the configured provider kind. In listening
tests, `gemini-2.5-pro-tts` over-acted, or with a style became slow and flat;
`gemini-3.8-flash-tts` sounded natural with and without a style;
gpt-4o-mini-tts has an audible synthetic buzz in the model's own output.
Gemini takes `--style` literally: "unhurried pace" gives long pauses. Ollama
speech models refuse `--style` and a speed other than 1.

A `speech` model of provider kind `vllm-omni` (Fish Audio Drama 3) runs on
the local GPU: the first sentence starts its server, which loads for minutes
and stops when the command ends, so give it the whole script in one `synth`.
It has no speed. Its voice is `default` or a voice of `add-voice` stored with
`--text` (the transcript), which it clones. With `default` the model picks a
new speaker per request, so `synth` uses the first sentence's take as the
reference for the rest and writes it to the output directory as `voice.wav`
and `voice.txt`. For several commands in one voice (the scenes of one film),
voice the first, then pass `--voice <its out dir>/voice.wav` to the others. `--style` becomes inline tags of
the model: `--style whisper` sends `[whisper] <sentence>` (tags `whisper`,
`excited`, `sighs`). See `references/fish-drama-3.md`.

Use `chatterbox` when the narration must sound like a specific person, such
as the user ("in my voice"): run `voices --backend chatterbox` and pass the
person's voice name. If they have no voice yet, see "Cloned voices" below.

`--style` is a delivery instruction in plain words ("calm documentary
narrator, unhurried pace"); it is not spoken. Kokoro voices: those whose
name prefix the setting `VOICEOVER_KOKORO_LANGS` maps to an espeak language
(`af_`/`am_` American, `bf_`/`bm_` British English in the example config).

## Model routes

Before each model call, run `${CLAUDE_SKILL_DIR}/scripts/voiceover.sh routes`.
It prints, per task of this skill, `| task | when | model | why |` rows:
first the task's default row (its model in `config.yaml`), then the user's
escalation rows, then the shipped ones, without the rows whose model
`config.yaml` lacks. Use the default row and pass no `--model`. Take a
later row, and pass its `model` with `--model`, only when its `when`
condition holds for the request; the first such row wins. A model that
the user or a calling skill names is passed as given, without the table.

The routes cover the `speech` task. A matching escalation row selects
`--backend speech --model <model>`; otherwise the backend choice above holds.
`synth` refuses a `--model` whose provider kind differs from that of
`models.speech` without `--voice`, because the voice settings name voices of
the configured model. Then run `voices --backend speech --model <model>` and
pass one of its voices with `--voice`.

## Script format

Plain text, one sentence per line. Blank lines are skipped. Lines are not
split further: sentence `n` in `timing.json` is the `n`-th non-blank line.
Write numbers the way they should be read; `1995` alone is read as a year,
`42%` as "forty-two percent".

## Commands

```bash
# First run: download the weights (Kokoro 350 MB, MMS_FA 1.26 GB) to the plugin's data directory
# (synth with another backend downloads only MMS_FA)
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh setup

# Script -> DIR/narration.wav + DIR/timing.json (prints both paths)
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh synth --script script.txt --out-dir out/

# Options
#   --backend kokoro|chatterbox|speech   default kokoro
#   --voice NAME     default per backend     --speed 1.0 (kokoro; speech except Gemini TTS)
#   --style TEXT     delivery instruction (speech only)
#   --model ID       <provider>:<model> of config.yaml (speech only; default: its speech model)
#   --lead 0.25      silence before the first sentence (s)
#   --gap 0.35       silence between sentences (s)
#   --tail 0.6       silence after the last sentence (s)
#   --no-align       sentence times only, no word alignment

# List the voices of a backend (default kokoro), the backend's default voice
# marked `(default)`; with chatterbox: `default` plus every recording
# (.wav/.flac/.mp3/.m4a) in the voices directory
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh voices [--backend kokoro|chatterbox|speech] [--model ID]

# Store a recording (.wav/.flac/.mp3/.m4a, longer than 5 s) as a chatterbox voice:
# copied to <voices dir>/NAME.<suffix of the recording>; prints the path
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh add-voice NAME recording.wav [--force] [--text "transcript"]

# Listen (macOS: VLC; Linux: xdg-open, the default application)
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh play out/narration.wav
```

`synth` downloads missing weights itself; `setup` only moves the wait earlier.
Set `VOICEOVER_MODEL_DIR` to store weights elsewhere. Play the result to the
user with `play`. Do not use QuickTime or a bare `open`.

## Cloned voices

The `chatterbox` backend (Chatterbox-Turbo, Resemble AI, English, MIT) clones
a voice from one reference recording, with no transcript and no training. A
voice is `<name>.wav`, `.flac`, `.mp3` or `.m4a` in the voices directory,
`VOICEOVER_VOICES_DIR` (default `<model dir>/voices`, model dir `VOICEOVER_MODEL_DIR`,
default under the plugin's data directory); `--voice` also takes a path to a recording;
`default` is the model's built-in voice. The model uses the first 10-15 s of
the recording, which must be longer than 5 s.

It copies the recording's delivery, microphone and room as well as the
speaker, so the recording decides the result. To make one: the person reads
15-20 s of plain prose aloud (any text; the opening of Fairbanks' Rainbow
Passage is a common choice) in the delivery wanted for the narration, close
to the microphone in a quiet room. On macOS record with
`ffmpeg -f avfoundation -list_devices true -i ""` (pick the microphone index)
and `ffmpeg -f avfoundation -i ":N" -ac 1 -ar 24000 -t 25 rec.wav`. On Linux
record with `ffmpeg -f alsa -i default -ac 1 -ar 24000 -t 25 rec.wav`. Then cut
breaths and silence at both ends and raise a quiet recording to about −20 LUFS
(e.g. `highpass=f=70,afftdn=nf=-70:nr=10,loudnorm=I=-20:TP=-2`) before
`add-voice`. Light denoising only: the model copies artefacts.

The weights (3 GB) come from the ModelScope mirror on first use, or with
`setup --chatterbox`. One sentence takes about 3 s per second of audio on
CPU. Output carries Resemble's inaudible Perth watermark. Clone only a voice
whose owner has agreed.

## `timing.json`

```json
{
  "audio": "narration.wav", "sample_rate": 24000, "duration": 9.02,
  "backend": "kokoro", "voice": "af_heart", "speed": 1.0,
  "sentences": [
    {"index": 1, "text": "Count to five.", "start": 0.25, "end": 1.31, "aligned": true,
     "words": [{"text": "Count", "start": 0.27, "end": 0.55}, ...]}
  ]
}
```

Times are seconds from the start of the file, rounded to milliseconds. Word
`text` is the word as written, punctuation included. A word with nothing to
pronounce (a dash, `&`) gets start = end = the previous word's end. If
alignment fails for a sentence, its words are spread over the sentence by
character length, `aligned` is `false`, and a warning goes to stderr; check
those sentences by ear before relying on their word times.

## Limits

English only (the voices and the text normalisation are English). Each
sentence is synthesised separately; with the `speech` models, tone can drift
a little between sentences. Gemini's length varies from run to run for the same
text.
