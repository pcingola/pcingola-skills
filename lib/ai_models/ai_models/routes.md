# Model routes: shipped escalations

The default model of a task is `models.<task>` of `config.yaml`. These rows are escalations from it: a row
applies only when its `when` condition holds for the request. The user's `routes.md` (next to `config.yaml`)
comes before these rows. A row whose provider or local model is not in `config.yaml` is left out. Times are
wall time per output on an NVIDIA GB10 (128 GB unified memory).

| task | when | model | why |
|---|---|---|---|
| image | only when the image must contain legible, correctly spelled text (posters, titles, labels, signs) | local:qwen-image | spells short text correctly where FLUX.2 klein and Z-Image-Turbo misspell it; about 2.3 min per 2K image, 9x FLUX.2 klein |
| image | only when the user asks for the highest image quality and accepts a longer wait | local:qwen-image | slightly more detail than FLUX.2 klein in photoreal and illustration; 9x slower |
| video | only when the clip has fast or complex motion (turbulent water, moving animals or people, objects interacting) and a long render is acceptable | local:kandinsky-6 | follows motion prompts more closely than LTX-2.5, which tends to slow fast motion down and smear fast-moving areas; about 14 min per 5 s clip, 9x LTX-2.5; can add stray objects; animals over water deform in every tested model |
