# Fish Audio Drama 3 (provider kind fish)

Fish Audio Drama 3 (`fishaudio/drama-3`, a 35B mixture of experts, 39 GB) is a local speech model that fish-speech
runs in the voiceover process on an NVIDIA GPU (Linux only). It is used when `tasks.speech` of `config.yaml`, or
`--model`, names a model of a provider of kind `fish`. voiceover installs the CUDA build of PyTorch and fish-speech
when `config.yaml` has such a provider.

## Running

- One `synth` loads the model once: the first sentence loads it (about 4 min on a GB10, reading 39 GB from disk),
  and it stays loaded until the command ends. A command per sentence loads the model per sentence.
- The load takes the local-model lock, so a short-video render or another local GPU model waits for it, and it
  waits for them (`local_models.lock_wait` of `config.yaml` limits the wait; unset, no limit).
- The load needs `memory` GB free, `providers.<p>.models.<m>.memory` (default 44, Drama 3's peak). When less memory
  is free and local Ollama models that Ollama unloads within 15 minutes hold the shortfall, `synth` prints the time
  it waits until and loads after they unload. Otherwise it fails before the load with an error that names what
  holds the memory: Ollama models with the time Ollama unloads each, and the largest processes. Models of other
  programs are theirs to unload.
- After the load, about 5 s of speech takes 4 to 9 s.
- It has no speed (`--speed` other than 1 fails) and takes no `--param`.

## Voice

- The model takes no recording; a chatterbox model clones one. A recording, or the name of a recording of
  `add-voice`, given as `--voice` or `--speaker NAME=VOICE` fails before the load.
- Without a reference the model makes up a new speaker for each request, and a fixed seed does not keep it. So
  `synth` keeps the first take of each speaker as the reference of that speaker's later sentences, and writes it to
  the output directory as `voice.wav` with its transcript `voice.txt`.
- With the voice `default` (no `--voice`) the made-up voice lasts one command. Another command, such as another
  scene of a film, makes up another voice.
- A Fish voice name (`--voice NAME`, `--speaker SPEAKER=NAME`; lowercase letters, digits, `-`, `_`) keeps a voice
  across commands. The first command with a new name saves the first take of that voice in the voices directory
  as `NAME.fish/` and prints `saved Fish voice` on stderr; every later command with that name starts from the saved
  take, so all its sentences have that voice. `voices --model <fish model>` lists the saved names. To get a
  different voice for a name, delete its `NAME.fish/` folder; the next command saves a new one.
- The saved voice is the first sentence spoken with that name, with its tags and style. A plain sentence in the
  delivery the voice should keep makes a better first take than a whispered or laughing one.

## Direction: point tags

Direction goes into the text as tags in square brackets, at the place in the line where the event should land:
`Fine. [laughs] Well, maybe that's fair.` Tags of the model card: `sighs`, `laughs`, `whisper`, `excited`. `synth`
sends every line to the model with its tags, anywhere in the line, and aligns the line without them (`timing.json`
keeps the text without tags as `text` and the line as sent as `said`). The model card reports that a tag at the
start of a line more often gives a silence after the first word.

The model ends a request with one tag on its own; with two tags in one request it speaks the text and then
near-silence to the length cap. So a line is cut before each tag and each part is one request, the parts joined
in order. In English, Spanish and French, and with `[whisper]` or `[laughing]`, each part ended on its own.

`--style TAG` sends `[TAG] <sentence>` for every part without a tag of its own (the model's `style` format in
`config.yaml`, `providers.<p>.models.<m>.style`; without `style` the model refuses `--style`). A plain-word style
("calm documentary narrator") becomes one bracketed tag; how the model reads such a tag is not measured.

## Dialogue: several speakers

A line that starts with `@<name> ` (lowercase letters, digits, `-`, `_`) is spoken by that speaker; a line without
it by the narrator. Each speaker gets a made-up voice: its first line gets a new voice from the model, and that
take is the reference of all its later lines, so the speaker keeps one voice for the command. `synth` writes the
take as `voice-<name>.wav` with `voice-<name>.txt` and names the made-up speakers on stderr; a misspelled `@name`
in the script is a new speaker. `--speaker host=anna` gives the speaker `host` the Fish voice `anna` instead, kept
across commands as above.

```
@host Welcome back to the show.
@guest Thanks for having me. [laughs] I have waited years for this.
```

The model also takes speaker tags inside one line, `<|speaker:0|>` to `<|speaker:15|>`: `synth` sends them as
written and leaves them out of the aligned text. A speaker tag at the start of a part stays in force for the
following parts of the same line; text without a tag is `<|speaker:0|>`. Each tag number of a line's speaker gets
its own made-up voice, kept for the command: `<|speaker:1|>` in narrator lines is one voice in every narrator line,
another than the narrator's, and another than `<|speaker:1|>` in `@guest` lines. Only the untagged voice of a
speaker (`<|speaker:0|>`) is written as `voice-<name>.wav` and saved as a named Fish voice; the voices of other
tag numbers last one command, so a voice that must last across commands needs its own `@name`.
