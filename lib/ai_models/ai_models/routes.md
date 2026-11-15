# Model routes: defaults

Rows are read in order; the agent takes the first row whose task is the call's task and whose `when`
describes the request. Rows of the user's `routes.md` (next to `config.yaml`) come before these. A row
whose provider or local model is not in `config.yaml` is left out. Times are wall time per output on an
NVIDIA GB10 (128 GB unified memory).

| task | when | model | why |
|---|---|---|---|
| image | text that must be spelled correctly: posters, titles, labels | local:qwen-image | the only tested model that spelled the test poster text right; about 2.3 min per image at 2K |
| image | quality matters more than time: a final hero image, print | local:qwen-image | a small quality gain over FLUX.2 klein in the photoreal and illustration tests, about 9 times slower |
| image | any other image: photoreal, illustration, drafts, everyday use | local:flux2-klein-4b | about 16 s per image at 2K; best of the tested models on the watercolour illustration test, near Qwen-Image on photoreal |
| video | a specific motion is asked for and render time is not a concern | local:kandinsky-6 | best prompt following of the tested models; about 14 min per 5 s clip |
| video | any other clip | local:ltx-2.5 | about 1.5 min per 5 s clip; generates an ambient sound track |
