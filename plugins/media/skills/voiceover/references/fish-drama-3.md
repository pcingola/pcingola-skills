# Fish Audio Drama 3 (speech backend, provider kind vllm-omni)

Fish Audio Drama 3 (`fishaudio/drama-3`) is a local speech model served by vLLM-Omni. It is used through the
`speech` backend when the `speech` task of `config.yaml` names a provider of kind `vllm-omni`.

## Running

- One `synth` loads the model once: the first sentence starts the server and waits for it to load; the server
  stops when the command ends. A command per sentence loads the model per sentence.
- The server takes the local-model lock, so a short-video render or another local model waits for it, and it
  waits for them.
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

## Direction

The model has no style field. Direction goes into the text as inline tags in square brackets. `--style TAG`
sends `[TAG] <sentence>` for every sentence (the provider's `style` format in `config.yaml`). Tags of the model
card: `whisper`, `excited`, `sighs`. The model card reports that a tag at the start of a line more often gives a
silence after the first word. A plain-word style ("calm documentary narrator") becomes one bracketed tag; how
the model reads such a tag is not measured.

Tags written into script lines are spoken as direction too, but the word aligner then looks for the tag words in
the audio, and the alignment of that sentence fails unless `--no-align` is given.
