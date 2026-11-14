# classify

Questions are Pydantic-AI's decision questions (`pydantic_ai.models.decision`). The models and providers are in
`ai_models` (`docs/ai_models.md`).

## Backends and models

`system1` sends each item with all questions to a System-1 model through `ai_models.system1.decide` and gets
probabilities per class. `chat` asks a chat model through a Pydantic-AI agent with native structured output (the
provider's JSON schema mode, since small models fail tool calls) and gets a label without probabilities. The chat
backend takes choice and noul questions only; a score question is refused before any request.

Without `--backend` the backend is `system1` when `config.yaml` has `models.system1`, else `chat`
(`backends.default_backend`). The model is `--model`, else `models.system1` or `models.chat`. The backend name goes
into the records, so a rerun with the other backend is refused by the backend check of the resume. `--timeout`
replaces the provider's `timeout` for each request.

## Question checks

`questions.check` refuses before any request what a model would refuse or answer badly: fewer than 2 classes, more than
10 score levels, repeated levels, empty names or descriptions, and a noul question with only one side described.
`questions.from_file` refuses keys other than `type`, `instructions` and `criteria` in a question, since a model
ignores unknown keys. Limits per model family (questions per request, options per choice) are the server's: a request
over a limit gets the server's message.

## Fail fast

The first item runs alone. An `AIModelsError` there (model not pulled, provider not reachable, key not set) exits once
with its message, so a run of many items does not record the same failure for each.

## Retries

The sequential passes after the concurrent pass retry only Pydantic-AI's `ModelRateLimitError` (HTTP 429) and
`ModelConnectionError`, also when `ai_models.errors.explained` wraps them, since these can clear with time. Any other
error, such as HTTP 400, would fail again. A chat answer that fails the output schema is retried by Pydantic-AI inside
the agent run; a System-1 answer that fails Pydantic-AI's answer check is not retried. A failed item's `request_id`
is null.

## Output file and resume

Each line is flushed as its item finishes, so a crash or a kill loses at most the requests in flight. An interrupted
run (Ctrl-C) skips the final rewrite and leaves the file in completion order; on the interrupt the queued items are
cancelled and the outcomes of requests already in flight are still written.

Each refusal of a rerun has its reason:

- Ids not among the items: the final rewrite keeps only the current items' ids, so those lines would be deleted.
- A successful line from another backend, or answering other question ids: the file would mix answers of different
  sources, which `eval` would then measure as one classifier. Failed lines are exempt, since they are scored again.

The check compares backend names and question ids only. A changed model, changed instructions or changed options under
the same question id are not detected.

## eval

Scoring, a resume and `--scores` all produce output records, and `eval` computes its metrics from those records in
every case: each record's answer goes through `backends.answer_parts` to a prediction, and the predictions through
`metrics.evaluate`. The final rewrite of `eval --out` recomputes `label` and `correct` from the current labelled file,
so resumed lines get the current labels too.

The Brier score of a yes/no question uses P(yes) alone; for choice and score questions it sums over classes, so a
two-option choice scores twice the yes/no value for the same probabilities. The last of the 10 `p_top` bins includes
1.0.

## Python use from skills of the ai plugin

A skill inside the `ai` plugin declares `ai-models` and `plugin-settings` as
dependencies with git sources in its `pyproject.toml` (`[tool.uv.sources]`
entries `{ git = "https://github.com/pcingola/pcingola-skills", subdirectory = "lib/ai_models", branch = "main" }`
and the same with `subdirectory = "lib/plugin_settings"`) and calls the library
directly; skills of other plugins load `ai:classify` with the Skill tool and use
the CLI.

```python
from ai_models import system1
from plugin_settings import Plugin
from pydantic_ai.models.decision import ChoiceQuestion

Plugin.of(__file__).load()   # settings of the plugin that holds this file
questions = {"team": ChoiceQuestion(instructions="Which team should handle this ticket?",
                                    criteria={"billing": "invoices, refunds", "technical": None, "sales": None})}
# model=None: models.system1 of config.yaml; or a "<provider>:<model>" id
answer = system1.decide(ticket_text, questions).answers["team"]
answer.choice, answer.probabilities[answer.choice]   # "billing", 0.997
```

`decide` raises `ai_models.errors.AIModelsError` for a missing config, model
or server, and Pydantic-AI's `ModelAPIError` subclasses for HTTP errors.
