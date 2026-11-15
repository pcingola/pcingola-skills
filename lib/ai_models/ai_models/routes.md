# Model routes: shipped escalations

The default model of a task is `models.<task>` of `config.yaml`. These rows are escalations from it: a row
applies only when its `when` condition holds for the request. The user's `routes.md` (next to `config.yaml`)
comes before these rows. A row whose provider or local model is not in `config.yaml` is left out. Times are
wall time per output on an NVIDIA GB10 (128 GB unified memory).

| task | when | model | why |
|---|---|---|---|
| image | only when the image holds text that must be spelled correctly (posters, titles, labels) | local:qwen-image | the only tested model that spelled a poster's text right; about 2.3 min per 2K image, 9x FLUX.2 klein |
| image | only when the user asks for the highest quality and accepts the wait | local:qwen-image | small gain over FLUX.2 klein in photoreal and illustration tests; 9x slower |
| video | only when the clip needs a specific motion that the default failed to produce | local:kandinsky-6 | best prompt following of the tested models; about 14 min per 5 s clip |
