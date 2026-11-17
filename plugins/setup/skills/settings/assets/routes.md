# Model routes

The template of the user's `routes.md`, which `setup:settings` copies next to `config.yaml`. Each task has a
`default` row, the recommended model, followed by rows that apply only when their `when` condition holds for the
request. The model in use for a task is `tasks.<task>` of `config.yaml`. A row whose provider or local model is not
in `config.yaml` is left out. Times are wall time per output on an NVIDIA GB10 (128 GB unified memory).

| task | model | when | why |
|---|---|---|---|
| image | local:flux2-klein-4b | default | about 16 s per 2K image; good photoreal and illustration; misspells text |
| image | local:qwen-image | only when the image must contain legible, correctly spelled text (posters, titles, labels, signs) | spells short text correctly where FLUX.2 klein and Z-Image-Turbo misspell it; about 2.3 min per 2K image, 9x the default |
| image | local:qwen-image | only when the user asks for the highest image quality and accepts a longer wait | slightly more detail than the default in photoreal and illustration; 9x slower |
| image | local:z-image-turbo | only when a photoreal image from the default is not good enough and Qwen-Image's wait is too long | marginally better than the default on photoreal only; looks artificial on illustration; misspells text; about 40 s per 2K image |
| video | local:ltx-2.5 | default | about 1.5 min per 5 s clip; good on calm scenes with small motion; generates ambient sound; slows fast motion down and smears fast-moving areas |
| video | local:kandinsky-6 | only when the clip has fast or complex motion (turbulent water, moving animals or people, objects interacting) and a long render is acceptable | follows motion prompts more closely than the default; about 14 min per 5 s clip, 9x the default; can add stray objects; animals over water deform in every tested model |
| video | local:ltx-video | only when the motion is slow and near-static and render time matters more than quality | about 1 min per 5 s clip; no sound; fast motion pixelates and deforms |
| speech | kokoro:kokoro-v1.0 | default | calm, clear voice that suits presentations (female voice af_heart preferred over the male voices in a listening test); about 10 s for three sentences on the CPU; English only (US and UK voices); no style or emotion control |
| speech | fish:drama-3 | only when the narration is in a language other than English, or needs a tone or emotion (whisper, excited, sighs, a described delivery) | multilingual; inline direction tags change the delivery; one made-up voice per speaker, kept from its first sentence (no cloning); NVIDIA GPU only; about 4 min load per command (44 GB), then about 5 s of speech in 4 to 9 s; the load waits for or fails on other models that hold GPU memory |
| speech | chatterbox:chatterbox-turbo | only when the narration must sound like a specific person who has a reference recording ("in my voice") | clones the voice from one recording longer than 5 s, with its delivery, microphone and room; about 2.5 to 4 s per short sentence on the CPU; no speed or style |
| presenter | local:kandinsky-s2v | only when the user asks for a talking presenter | lip sync has gaps and the mouth over-articulates; about 23 min per 4 s |
| music | local:ace-step-sft | default | ACE-Step 1.5 XL SFT, 50 steps; about 12 s per 30 s clip; clean dynamics |
| music | local:ace-step | only when a quick draft is enough and saturated, compressed sound is acceptable | ACE-Step 1.5 XL turbo, 8 steps; about 2 s per 30 s clip; loud and compressed, audibly distorted on calm music |
