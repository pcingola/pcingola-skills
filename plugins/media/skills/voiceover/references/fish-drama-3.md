# Fish Audio Drama 3 (provider kind vllm-omni)

Fish Audio Drama 3 (`fishaudio/drama-3`) is a local speech model served by vLLM-Omni. It is used when
`tasks.speech` of `config.yaml`, or `--model`, names a model of a provider of kind `vllm-omni`.

## Running

- One `synth` loads the model once: the first sentence starts the server and waits for it to load; the server
  stops when the command ends. A command per sentence loads the model per sentence.
- The server takes the local-model lock, so a short-video render or another local model waits for it, and it
  waits for them.
- The server takes `memory` GB of the model entry, `providers.<p>.models.<m>.memory` (Drama 3: 70), plus `overhead` GB outside it (default 22). When less
  memory is free and local Ollama models that Ollama unloads within 15 minutes hold the shortfall, `synth` prints
  the time it waits until and starts after they unload. Otherwise it fails in about a second, before the load,
  with an error that names what holds the memory: Ollama models with the time Ollama unloads each, and the largest
  processes. Models of other programs are theirs to unload.
- It has no speed (`--speed` other than 1 fails).

## Voices

- `default`: the model's own voice. Without a reference the model picks a new speaker for each request (median
  F0 110, 184 and 191 Hz for three sentences). A fixed `seed` does not keep the speaker either, because the
  speaker changes with the text (seed 7: 184, 146 and 135 Hz). So `synth` sends the first sentence without a
  reference and uses that take as `ref_audio`/`ref_text` for the rest (138, 138 and 148 Hz), and writes it to
  the output directory as `voice.wav` with its transcript `voice.txt`.
- One voice across commands (the scenes of one film): voice the first scene with `default`, then give every other
  scene `--voice <first scene's out dir>/voice.wav`.
- A reference voice keeps one speaker across sentences: `add-voice NAME recording.wav --text "what the recording
  says"` stores the recording and its transcript; `--voice NAME` (or a path to a recording with a `.txt`
  transcript of the same name beside it) clones it.

## Direction: point tags

The model has no style field. Direction goes into the text as tags in square brackets, at the place in the line
where the event should land: `Fine. [laughs] Well, maybe that's fair.` Tags of the model card: `sighs`, `laughs`,
`whisper`, `excited`. `synth` sends every line to the model as written, tags included, anywhere in the line, and
aligns the line without them (`timing.json` keeps the text without tags as `text` and the line as sent as
`said`). The model card reports that a tag at the start of a line more often gives a silence after the first word.

`--style TAG` sends `[TAG] <sentence>` for every sentence (the model's `style` format in `config.yaml`, `providers.<p>.models.<m>.style`). A
plain-word style ("calm documentary narrator") becomes one bracketed tag; how the model reads such a tag is not
measured.

## Dialogue: several speakers

A line that starts with `@<name> ` (lowercase letters, digits, `-`, `_`) is spoken by that speaker; a line without
it by the narrator (`--voice`). Each line is one request.

- A speaker with a voice: `--speaker NAME=VOICE`, VOICE a voice of `add-voice` stored with `--text` or the path of
  any recording with its transcript in a `.txt` file of the same stem. The model clones it for every line of that
  speaker.
- `synth` checks every `--speaker` before the server starts: the name must be a speaker name used by an `@name`
  line, and its recording must exist with its transcript. A misspelled `@name` in the script is a new made-up
  speaker; `synth` names the made-up speakers on stderr.
- A made-up speaker: no `--speaker` for it. Its first line gets a new voice from the model, and that take is the
  reference of all its later lines, so the speaker keeps one voice for the command. `synth` writes the take as
  `voice-<name>.wav` with `voice-<name>.txt`; `--speaker NAME=<out dir>/voice-<name>.wav` keeps the voice in
  later commands.

```
@host Welcome back to the show.
@guest Thanks for having me. [laughs] I have waited years for this.
```

On the GB10, four lines of two made-up speakers took 314 s, 281 s of them the server load; the host's lines had
median F0 192 and 176 Hz, the guest's 255 and 248 Hz, and all four aligned with their tags left out.

The model also takes speaker tags inside one line, `<|speaker:0|>` to `<|speaker:15|>`: `synth` sends them as
written and leaves them out of the aligned text. In one request the reference (the line's voice) is speaker 0;
the other indexes get made-up voices for that request only.

## Request fields

`--param KEY=VALUE` (repeatable) adds a field to every request, VALUE as JSON when it parses. The vLLM-Omni speech
endpoint of this version reads, for Drama 3: `seed` (an integer), `max_new_tokens`, and `extra_params`, an object
whose `temperature`, `top_p` and `top_k` set the sampling (`--param 'extra_params={"temperature": 0.8,
"top_p": 0.9}'`); the model card's benchmark used temperature 1.0, top_p 0.9, top_k 30. The server ignores a
field it does not know. A fixed `seed` does not keep the speaker without a reference (see Voices).

Not available through vLLM-Omni 0.32: `previous_takes` (editing as continuation) and several references in one
request. The model card shows both on SGLang-Omni's `/v1/tts`, not on vLLM-Omni's `/v1/audio/speech`, whose Drama 3
adapter takes one reference (`ref_audio`, `ref_text`) or its codec codes (`ref_audio_codes`).
