---
name: voiceover
description: "Generates narration audio from a script with sentence and word timings, with the speech models of config.yaml (Kokoro, Chatterbox cloning, API). TRIGGER when: user asks for a voiceover, narration, TTS, a cloned voice, 'in my voice', or word timings."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/voiceover.sh:*) Read Skill
metadata:
  version: "0.1.0"
---

# Voiceover

Turns a script into `narration.wav` plus `timing.json` with the start and
end of every sentence and every word. A speech model of the settings file
`config.yaml` synthesises each sentence: `--model <provider>:<model>`, else
the model of the `speech` task. The model of the `align` task (torchaudio's
MMS_FA, local, CPU) force-aligns each sentence against its known text to get
word times.

What the speech model takes depends on the kind of its provider:

| kind | runs | default voice | speed | style |
|---|---|---|---|---|
| `kokoro` | local CPU, Kokoro 82M | `af_heart` | 0.5 to 2 | no |
| `chatterbox` | local CPU, Chatterbox Turbo, clones a voice | `default` | no | no |
| `fish` | local NVIDIA GPU, Fish Audio Drama 3, one made-up voice per speaker | `default`, the only voice | no | inline tags |
| `openai`, `azure`, `openrouter` | API, `audio/speech` | `marin` | 0.25 to 4 | yes |
| `ollama` | Ollama `audio/speech` | `default` | refused by the server | refused by the server |
| `google` | API, Gemini TTS | `Kore` | no | yes |

A model's `voice` in `config.yaml` (`providers.<p>.models.<m>.voice`) replaces the default voice. `synth`
refuses a speed or a style the model does not take before any request.

Use the `speech` model unless the routes or the user say otherwise. A Kokoro
model sounds calm and clear and takes about 10 s for three sentences. The
provider checks the voice of an API model; `voices` lists the voices of a
model. In listening tests, `gemini-2.5-pro-tts` over-acted, or with a style
became slow and flat; `gemini-3.8-flash-tts` sounded natural with and without
a style; gpt-4o-mini-tts has an audible synthetic buzz in the model's own
output. Gemini takes `--style` literally: "unhurried pace" gives long pauses.
Ollama's `lfm3-audio` has odd, uncontrolled intonation: it is for tests, not
for narration.

A model of provider kind `fish` (Fish Audio Drama 3) runs on the local
NVIDIA GPU in the voiceover process: the first sentence loads it (about
4 min, 44 GB) and it stays loaded until the command ends, so give it the
whole script in one `synth`. Its only voice is `default`: the model makes
up a speaker, and `synth` keeps the first sentence's take as the reference
of the rest and writes it to the output directory as `voice.wav` and
`voice.txt`. Another command makes up another voice, and the model takes
no recording; a voice that must stay the same across commands, or a
specific person's voice, needs a `chatterbox` model. Tags in square
brackets anywhere in a line (`Fine. [laughs] Well.`; `whisper`, `excited`,
`sighs`, `laughs`) direct the delivery at that point; `--style whisper`
sends `[whisper] <sentence>` for every line. It voices dialogue: `@<name>`
at the start of a line names its speaker, and each speaker gets a made-up
voice kept for all its lines. Read `references/fish-drama-3.md` before
using any of these.

When the narration must sound like a specific person, such as the user ("in
my voice"), use a model that clones a voice (the routes name one), run
`voices --model <model>` and pass the person's voice name. If they have no
voice yet, see "Cloned voices" below.

`--style` is a delivery instruction in plain words ("calm documentary
narrator, unhurried pace"); it is not spoken. Kokoro voices: those whose
name prefix the model's `langs` maps to an espeak language (`af_`/`am_`
American, `bf_`/`bm_` British English in the example config).

## Model routes

Before each model call, run
`${CLAUDE_SKILL_DIR}/scripts/voiceover.sh routes`. It prints, per task of
this skill, `| task | model | when | why |` rows from the user's
`routes.md` beside `config.yaml`: first the task's default row (`when` is
`default`, the model is the task's model in `config.yaml`, and `why` names
the table's recommended model when it differs), then the escalation rows,
without the rows whose model `config.yaml` lacks. Without the file it
prints only the default rows. Use the default row and pass no `--model`.
Take a later row, and pass its `model` with `--model`, only when its
`when` condition holds for the request; the first such row wins. A model
that the user or a calling skill names is passed as given, without the
table. The routes cover the `speech` task. Without `--voice`, `synth` uses
the default voice of the model it runs.

## Script format

Plain text, one sentence per line. Blank lines are skipped. Lines are not
split further: sentence `n` in `timing.json` is the `n`-th non-blank line.
Write numbers the way they should be read; `1995` alone is read as a year,
`42%` as "forty-two percent".

What else a line may carry depends on the model:

- A model that takes inline tags (Fish): `@<name> ` at the start names the
  speaker; tags in square brackets (`[laughs]`) and speaker tags
  (`<|speaker:1|>`) anywhere are sent as written and left out of the
  aligned text, so one `synth` (one model load) voices several speakers and
  directions. `timing.json` gives each sentence its `speaker` and, when the
  line had tags, `said` (the line as sent).
- A model that takes a style but no tags (OpenAI, Gemini): a line may start
  with its own style in square brackets, `[whisper] Keep it quiet.`, spoken
  with the style `whisper` instead of `--style`; `timing.json` records the
  sentence's `style`.
- Any other model (Kokoro, Chatterbox): plain text only. A line with `@name`
  or a tag is refused, since the model would speak it; so is `--speaker`.

`--param` is for the API kinds `openai`, `azure`, `openrouter` and `ollama`;
the other kinds refuse it. `synth` checks every line and every voice (each
`--speaker` name against the script, each recording) before the first
request. A speaker of the script without `--speaker` gets a made-up voice;
`synth` names those on stderr.

## Commands

```bash
# First run: download the weights of the speech model (local kinds: Kokoro
# 350 MB, Chatterbox 3 GB) and of the align model (MMS_FA 1.26 GB)
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh setup [--model ID]

# Script -> DIR/narration.wav + DIR/timing.json (prints both paths)
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh synth --script script.txt --out-dir out/

# Options
#   --model ID       <provider>:<model> of config.yaml (default: tasks.speech)
#   --voice NAME     default: the model's default voice; for a model that
#                    clones a voice also a voice of add-voice or a path
#   --speed 1.0      models with a speed setting
#   --style TEXT     delivery instruction, models that take one
#   --speaker NAME=VOICE   voice of the `@NAME` lines (models that take tags)
#   --param KEY=VALUE      one more request field, VALUE as JSON (repeatable;
#                          the openai, azure, openrouter and ollama kinds)
#   --lead 0.25      silence before the first sentence (s)
#   --gap 0.35       silence between sentences (s)
#   --tail 0.6       silence after the last sentence (s)
#   --no-align       sentence times only, no word alignment

# List the voices of a model (default tasks.speech), its default voice
# marked `(default)`; a model that clones a voice also lists every recording
# (.wav/.flac/.mp3/.m4a) in the voices directory
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh voices [--model ID]

# Store a recording (.wav/.flac/.mp3/.m4a, longer than 5 s) as a voice:
# copied to <voices dir>/NAME.<suffix of the recording>; prints the path
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh add-voice NAME recording.wav [--force]

# Listen (macOS: VLC; Linux: xdg-open, the default application)
${CLAUDE_SKILL_DIR}/scripts/voiceover.sh play out/narration.wav
```

`synth` downloads missing weights itself; `setup` only moves the wait earlier.
The weights directory of a local model is its provider's `dir` in
`config.yaml` (default `voiceover/` under the plugin's data directory).
Play the result to the
user with `play`. Do not use QuickTime or a bare `open`.

## Cloned voices

A model of provider kind `chatterbox` (Chatterbox-Turbo, Resemble AI,
English, MIT) clones a voice from one reference recording, with no
transcript and no training. A voice is `<name>.wav`, `.flac`, `.mp3` or
`.m4a` in the voices directory, `voiceover.voices_dir` of `config.yaml` (default
`voiceover/voices` under the plugin's data directory); `--voice` also takes
a path to a recording; `default` is the model's built-in voice. The model
uses the first 10-15 s of the recording, which must be longer than 5 s.

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

It runs on the CPU in the voiceover process; the user adds the template's
`chatterbox` provider entry to `config.yaml` (setup:settings). The weights
(3 GB) come from the `url` of the model entry on first use, or with
`setup --model <model>`. The load takes about 10 s, and a short sentence
2.5 to 4 s. Output carries Resemble's inaudible Perth watermark. Clone only a voice
whose owner has agreed.

## `timing.json`

```json
{
  "audio": "narration.wav", "sample_rate": 24000, "duration": 9.02,
  "model": "kokoro:kokoro-v1.0", "voice": "af_heart", "speed": 1.0,
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
sentence is synthesised separately; with the API models, tone can drift
a little between sentences. Gemini's length varies from run to run for the same
text.
