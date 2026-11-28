"""An OpenAI-compatible server of the local models of config.yaml, with Ollama behind it (docs/model_server.md).

    app            `create_app`: the FastAPI app, its routes and its error bodies
    __main__       `python -m model_server`: uvicorn on `model_server.host` and `port`
    server         `Server`: settings, scheduler, residency, Ollama, video jobs
    model_ref      `ModelRef`: the routing of a request's `model` (`<provider>:<model>`)
    scheduler      `Scheduler`: one model at a time, one FIFO queue; `Lease`
    residency      `Residency`: keep-alive and room in memory before a load
    ollama         `Ollama`: forwarding and the memory calls of Ollama
    catalog        the local models as `openai.types.Model`
    routes_*       the endpoints: images, audio (speech, music, alignments), videos, models, Ollama forwarding
    client         `model-client`: a command-line client of a server at a URL
"""

from .app import create_app

__all__ = ["create_app"]
