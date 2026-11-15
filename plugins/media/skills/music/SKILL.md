---
name: music
description: "Generates music with Lyria or local ACE-Step, loops or trims tracks, checks clips against a brief. TRIGGER when: user asks for music, a song, jingle, soundtrack, to loop/trim a track, or to analyze or compare generated music with a brief."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/music.sh:*) Read Skill
metadata:
  version: "0.1.0"
---

# Music

Generates music with the `music` model of the settings file `config.yaml`,
fits tracks to an exact length,
and checks clips against the brief they were made from.

```bash
${CLAUDE_SKILL_DIR}/scripts/music.sh generate "<prompt>" -o out.mp3 [options]
${CLAUDE_SKILL_DIR}/scripts/music.sh fit in.mp3 -o out.mp3 --seconds 45 [--fade-in 0] [--fade-out 2]
${CLAUDE_SKILL_DIR}/scripts/music.sh analyze <files or folder> [--brief "<style>"] [--prompts FILE] [--only model|signal|images]
```

## Models

The model is `--model <provider>:<model>`, else the config's `music` task.
Model routes (below) choose `--model`.

| Provider kind | Model | Output | Options |
|---|---|---|---|
| `google` | Lyria 3 (`lyria-3-pro-preview`, `lyria-3-clip-preview`) | MP3; Pro up to 184 s, Clip 30 s | `--image` `--lyrics` `--instrumental` `--bpm` `--seconds` (Pro) |
| `google` | `lyria-002` | WAV 48 kHz, about 33 s, instrumental only | `--negative` `--seed` `--samples` `--bpm` `--instrumental` |
| `diffusers` (local) | ACE-Step | WAV or MP3, `--seconds` exact (default 30) | `--lyrics` `--instrumental` `--bpm` `--seconds` `--seed` |

Pro for full pieces and songs; Clip for short loops, jingles and quick drafts;
lyria-002 for repeatable instrumentals (`--seed`) or several takes in one call
(`--samples N`, files `<stem>_1.wav` … `<stem>_N.wav`). ACE-Step runs on the
local GPU, gives the exact `--seconds` and sings only `--lyrics`: without
them the track is instrumental. Local models need the skill's `local` extra
(torch and diffusers, installed when the config has a `diffusers` provider)
and a CUDA or Apple MPS GPU; ACE-Step needs about 13 GB of GPU memory. An
option the model does not take is refused with the model kinds that take it.

`--out` ends in `.mp3` or `.wav`. A local model's WAV is encoded to MP3 with
FFmpeg for a `.mp3` output. When a Lyria model returns the other format, the
CLI writes the file with the suffix of that format, prints a warning and
prints the path it wrote. Existing files are not overwritten without
`--force`.

## Model routes

Before each model call, run `${CLAUDE_SKILL_DIR}/scripts/music.sh routes`.
It prints the routing table of this skill's tasks, `| task | when | model | why |`:
the user's rows, then the default rows, without the rows whose model
`config.yaml` lacks. Take the first row whose task is the call's task and
whose `when` describes the request, and pass its `model` with `--model`.
With no matching row, pass no `--model`: the task's model of `config.yaml`
serves the call. A model that the user or a calling skill names is passed
as given, without the table.

The task of the call is `music` for `generate` and `audio` for `analyze`.

## Options

- `PROMPT` or `--prompt-file FILE`: the description of the music.
- `--image PATH` (repeatable, up to 10, PNG/JPEG/WebP): Lyria 3 composes for
  the picture(s).
- `--lyrics FILE`: sung lyrics with section tags (`[Verse]`, `[Chorus]`,
  `[Bridge]`, `[Outro]`), one line per sung line. Not with `--instrumental`.
- `--instrumental`: no vocals.
- `--bpm N`: tempo. `--seconds N` (Pro, ACE-Step): length. Pro follows the
  length loosely; use `fit` for an exact length.
- `--negative TEXT`: what to leave out (lyria-002).
- `--seed N` (lyria-002, ACE-Step) or `--samples N` (lyria-002), not both.

Lyria has no request fields for tempo, length, vocals or lyrics. The CLI
writes the tempo and "instrumental" into the prompt; the model layer adds the
length and the lyrics block for Lyria 3. `<out>.json` records the prompt the
CLI sent. ACE-Step takes lyrics, length and seed as arguments; the tempo is
appended to the prompt as a tag (`, 110 bpm`).

## Output

- the audio file(s), paths printed on stdout;
- `<out>.json`: model, prompt sent, options, MIME type, finish reason,
  duration, and the lyrics when given;
- `<out>.txt` (Lyria 3): the text the model returned, i.e. the generated
  lyrics or song structure.

Play results with `open -a VLC <file>` on macOS and `xdg-open <file>` on Linux.

## Writing Lyria 3 prompts

Name the genre and style, the instruments, the mood, and the arrangement:
"Warm lo-fi hip hop with dusty vinyl crackle, mellow Rhodes chords, soft
boom-bap drums and a muted bass line; relaxed, late-night mood." For vocals,
name the voice ("breathy female vocal", "male baritone") and the language.

Structure can be set with section tags in the lyrics, or with timestamps in
the prompt for Pro:

```
[0:00 - 0:15] Intro: solo piano, sparse.
[0:15 - 0:45] Verse: drums and bass enter, gentle groove.
[0:45 - 1:15] Chorus: full band, strings, uplifting.
```

lyria-002 takes a plain description; put unwanted elements in `--negative`
rather than writing "no drums" in the prompt.

ACE-Step takes the prompt as comma-separated style tags: genre, instruments,
mood, vocal type ("synthwave, female vocals, dreamy, analog pads").

## Fit

`fit` loops a track (`-stream_loop`) or trims it to `--seconds`, applies a
fade-in (default 0 s) and fade-out (default 2 s), and encodes by the output
extension (`.mp3`, `.wav`, `.m4a`). Fades longer than the target are refused.
Needs FFmpeg.

## Analyze

`analyze` takes audio files (`.wav`, `.mp3`, `.flac`, `.m4a`, `.aac`,
`.ogg`) and folders (their audio files, not subfolders) and writes, for each
clip, a report and two images to `<folder>/analysis/` (`--out-dir DIR` to
choose; required when inputs come from several folders). Input files are only
read; an `--out-dir` that holds input files is refused. Three analyses run,
all by default; `--only` (repeatable) selects some, and a rerun updates those
sections of an existing report and keeps the rest.

- `model`: the clip is sent inline (WAV, MP3, FLAC, OGG up to 14 MiB as they
  are, WAV and MP3 only on providers other than `google`; other files as a
  mono 128 kb/s MP3) to a chat model that takes audio, in two requests with
  fixed prompts and JSON schemas. The first contains no
  brief and returns `genre`, `instruments`, `tempo_bpm`, `mood`, `energy`
  (low/medium/high), `energy_changes` and `energy_change_description`,
  `vocals` and `vocals_description`. The second, sent only when a brief
  exists, quotes that description and returns for the clip brief and the
  style brief a verdict (`fits`, `partly`, `does not fit`, `no brief`) with
  reasons. The model is `--model`, else the config's `audio` task (a Gemini
  model, for example). An answer without a required key is asked again.
  When the config names no `audio` model or lacks its provider, the section
  is `"status": "skipped"` with the reason and the run continues.
- `signal` (librosa, numpy, FFmpeg): tempo, beat confidence (autocorrelation
  of the onset envelope at the beat period, 0 to 1; also at the requested
  tempo), inter-beat-interval CV, `pulse` (regular ≥ 0.3, weak ≥ 0.15, none),
  percussive ratio (HPSS energy), onsets per second, mean spectral centroid,
  RMS in 2 s windows labelled `building`, `flat`, `decaying`, `sparse` or
  `silent`, key and mode (Krumhansl-Kessler on chroma; none for silence),
  integrated loudness, loudness range and true peak (EBU R128), and a
  one-line `summary`. Clips under 2 s get no tempo or key.
- `images`: `<clip>_spec.png` (log-frequency spectrogram with time and
  frequency scales) and `<clip>_wave.png` (waveform per channel). Read them
  to see structure, gaps, fades and clipping.

Briefs: `--brief` is the style brief every clip is judged against. Each
clip's own brief is its entry in `--prompts FILE`, else the `prompt` in the
`<file>.json` that `generate` wrote. A prompts file is a JSON object
(`{"a.mp3": "prompt"}`), one `a.mp3: prompt` line per clip, or blocks with a
`File: a.mp3` line and a `Prompt:` or `Prompt sent:` line; an entry matches
the file name, else the stem (one entry covers `a.mp3` and `a.wav`). Entries
that match no input and inputs with no clip brief are printed as warnings. The
requested tempo is the sidecar's `bpm`, else the first "N BPM" in the clip
brief, else in the style brief.

Output in `<out>/`: `<clip>.json` (`brief`, `model`, `signal`, `images`,
`checks`; `<clip>` is the stem, the file name when two inputs share a stem,
`<folder>_<file name>` when two share a name), the two PNGs, and `summary.md`, rebuilt from every report in the
folder: one paragraph per clip with the verdict, then measured vs requested
tempo, pulse and percussive ratio, the model's genre, mood, energy and
vocals, the key and loudness, the model's reasons, and flags (tempo differs
from the request, true peak above -1 dBTP, sparse or silent level, vocals in
an instrumental brief). A report missing fields gets a note in `summary.md`
instead of a paragraph. Exit status 1 when an analysis failed for some clip.

What the numbers mean:

- A low percussive ratio (under about 0.1) means no drums; drum-led clips
  measured 0.15 to 0.4. Beat confidence measures how periodic the onsets
  are, so repeated piano chords can score like a drum beat.
- Beat trackers often lock to half, double or another multiple of the
  played tempo; `checks.tempo.relation` names `half` and `double`. When the
  measured tempo differs, compare the beat confidence at the requested tempo
  with the one at the measured tempo: similar values mean the tempo is
  ambiguous rather than wrong.
- Take tempo and key from `signal`, not from the model description. Model
  verdicts vary between runs and between the MP3 and WAV of the same clip.

These checks measure fit to the brief and technical defects, not musical
quality. Present `summary.md` and the images, and leave the choice between
clips to the user, who listens to them.

## Notes

- All Lyria output carries Google's SynthID watermark.
- Lyria 3 output is MP3 only, and Lyria 3 has no seed.
- The providers, their keys and the `music` and `audio` models are in the
  `ai_models` config file. The skill has no model settings of its own.
