# music

The music skill generates music with the `music` model of `config.yaml` (Lyria on a `google` provider, or ACE-Step as
a local `diffusers` model), fits tracks to a length and checks clips against their briefs. The requests, Lyria's
behaviour and the local models are in `ai_models` (`docs/ai_models.md`).

## Generation

The model is `--model` (a `<provider>:<model>` id), else `models.music`. The skill has no aliases and no model table.
The wrapper installs the skill's `local` extra (`ai-models[diffusers]`) when the config has a provider of kind
`diffusers`.

`ai_models.music.compose` refuses, before any request, an option the model kind does not take (`music.TAKES`):

| Model kind | Options |
|---|---|
| `diffusers` (ACE-Step) | `--seconds`, `--lyrics`, `--seed` |
| `lyria-002` (`:predict`) | `--seed`, `--negative`, `--samples` |
| other Lyria models (Lyria 3, stream) | `--seconds`, `--lyrics`, `--image` (up to 10) |

`--seed` with `--samples` is refused. The endpoint can answer a bad streaming request with no cause, so refusing early gives
the only useful message. The skill no longer checks the `--seconds` range or the output extension per model; the
model refuses what it cannot do.

Lyria has no request fields for tempo or vocals, so `prompt.compose` writes them into the prompt. ACE-Step reads the
prompt as style tags, so `--bpm` is appended as a tag (`prompt.tags`) and `--instrumental` is the lyrics
`[instrumental]` (`prompt.local_lyrics`). Neither prompt gets the tempo when it already names it (`prompt.names_tempo`,
`110 bpm` in any case). The local model writes WAV; for an `.mp3` output FFmpeg encodes it
(`fit.encode`). With `--samples N` the files are `<stem>_1` ... `<stem>_N`. `<out>.json` records the model, the
prompt sent, the options, the MIME type and the finish reason (Lyria 3); `<out>.txt` holds the text Lyria 3 returns
with the audio (lyrics or song structure).

## Crest factor check

ACE-Step 1.5 XL turbo (`ACE-Step/acestep-v15-xl-turbo-diffusers`, 8 steps) generates loud, compressed audio; more
turbo steps did not change it. The XL SFT model (`ACE-Step/acestep-v15-xl-sft-diffusers`, 50 steps, guidance 7) takes
about 12 s per 30 s clip, and in a listening test SFT was clearly better. The config template's `models.music` is
therefore `local:ace-step-sft`; the turbo model `local:ace-step` stays for tests and quick drafts.

The crest factor (`measure.crest_db`) is sample peak minus RMS over the 2 s windows whose RMS is within 6 dB of the
loudest, on the track decoded in stereo at 48 kHz (`measure.track_crest_db`). The whole-file value counts quiet intros,
fades and silence. The pipeline peak-normalizes to -1 dBFS, so counting full-scale samples finds no clipping.
Measured on the review clips:

| clips | crest factor where loud (dB) |
|---|---|
| user-approved SFT corporate clip (30 s, 50 steps, guidance 7) | 14.7 |
| SFT A/B: corporate seeds 6 and 9 (guidance 7), seed 9 (guidance 4), rock seed 42 | 16.2, 10.9, 11.0, 15.8 |
| turbo, six genres (classical, corporate, jazz, rock, song, techno) | 9.2, 9.4, 13.7, 11.9, 12.6, 12.7 |
| turbo A/B, corporate seed 42 (8, 16, 32 steps, variants), seed 6, rock seed 42 | 12.6 to 13.5, 11.1 |
| turbo A/B, corporate seed 9 ("hot") | 9.1 |

The template sets `min_crest_db: 10` on the SFT entry: it passes every SFT clip and catches the hot seed 9 and the two
quietest turbo clips. The turbo entry has none, since it is chosen knowing its sound is compressed.

Because the crest factor depends on the seed, `generate` runs the check when `--min-crest-db` is above 0, or without
it when the model entry has `min_crest_db` (`ai_models.music.min_crest_db`; only diffusers entries exist, so remote
models get a check only from the option). Mastered rock, techno and EDM sit around 8 to 12 dB, so the threshold is per
model and per call, and the music skill tells the agent to pass 0 for those genres. `crest.regenerate` sends a request
with a track below the threshold again, up to `--crest-attempts` requests (default 3). A model whose kind takes a seed
(`ai_models.music.takes`) gets the next seed, the first being `--seed` or a random one; another, or a call with
`--samples`, gets the same request again. The first request with every track at or above the threshold is kept, else
the one with the highest lowest crest factor. The sidecar records every attempt and the kept `seed`. A failed
measurement keeps the tracks of that request, prints a warning and writes no `crest` entry. The code names no model;
model choices are in `config.example.yaml` and `routes.md`.

## Model description in analyze

The model is `--model`, else `models.audio`, a chat model that takes audio. Without either, the model section is
skipped with the reason, and the run continues.

The clip is sent inline. WAV, MP3, FLAC and OGG files up to 14 MiB go as they are (Gemini's inline limit of 20 MiB
after base64); larger files and every other type (M4A and AAC are often MP4 containers) are transcoded to a mono
128 kb/s MP3. Providers other than `google` get audio as the OpenAI `input_audio` part, which takes WAV and MP3 only,
so FLAC and OGG are transcoded there too.

With the brief in the same request, a model described a pure sine tone as the piano piece the brief asked for.
The description request therefore holds no brief, so the description is not primed by what was asked for; the verdict is a
second request, sent only when a brief exists, which quotes the description and the briefs. An answer that lacks a key
the schema requires is asked again.

Probed 2026-10-21 on Vertex AI, gemini-3.1-pro-preview, gemini-3.5-flash, gemini-3-flash-preview,
gemini-3.1-flash-lite, gemini-2.5-pro, gemini-2.5-flash and gemini-2.5-flash-lite accepted inline audio. All of them
misreported the pitch of a 440 Hz tone, and the tempo a model gave usually repeated the brief's. Probed 2026-10-23 on
the same clips, gemini-3.1-pro-preview:

| clip | answer |
|---|---|
| 0.5 s of silence | music |
| 440 Hz sine | A4 (440 Hz) |
| 120 BPM drum loop, three runs | 120, 128 and 192 BPM |

Tempo and key are therefore taken from the signal measurements.

## Signal measurements

librosa's onset strength is log-mel spectral flux in dB, and librosa normalises the envelope before peak picking, so a
steady tone yields many tiny onsets. Onsets below `ONSET_MIN` (1 dB) are dropped, and a clip whose 95th percentile of
onset strength is below it gets no tempo.

## Reruns

A rerun that gives no clip or style brief keeps the one in the existing report. The report's requested tempo is kept
only when both briefs are unchanged, since it may have been read from a brief that has since changed. The signal
section stores the `requested_bpm` its beat confidence at the requested tempo was computed for, because that
confidence depends on the brief; `summary.md` prints it only when it matches the report's current requested tempo, so
a model-only rerun with a new brief does not show a confidence for the old tempo.

## Inputs are never written

`analyze` names a report `<clip>.json`, where `<clip>` is the file name when two inputs share a stem. A report on
`a.mp3` in the folder of `a.mp3` and `a.wav` would then be `a.mp3.json`, the sidecar `generate` wrote for that clip,
which holds the prompt `analyze` reads as the clip brief. An `--out-dir` that holds input files is therefore refused.
