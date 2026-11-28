"""`GET /v1/jobs`, `DELETE /v1/jobs/{id}` and `DELETE /v1/jobs`: the jobs of the scheduler, every request that
waits for or holds a slot (images, speech, music, alignments, videos, presenters, Ollama), and their cancellation.

The list is `{"object": "list", "data": [JobInfo]}`, oldest first. `DELETE /v1/jobs/{id}` cancels one job and
answers it with `cancelled: true`, a 404 `job_not_found` for an id that is not queued or running; `DELETE /v1/jobs`
cancels every job and answers the list of the cancelled jobs. What a cancel does is in `Scheduler` and
docs/model_server.md, Jobs.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .job import Job
from .requests import server_of
from .server_error import ErrorType, ServerError

router = APIRouter()


def listed(jobs: list[Job]) -> JSONResponse:
    return JSONResponse({"object": "list", "data": [j.info().model_dump(mode="json") for j in jobs]})


@router.get("/v1/jobs")
async def list_jobs(request: Request) -> JSONResponse:
    return listed(server_of(request).scheduler.jobs())


@router.delete("/v1/jobs")
async def cancel_all(request: Request) -> JSONResponse:
    return listed(server_of(request).scheduler.cancel_all())


@router.delete("/v1/jobs/{job_id}")
async def cancel(job_id: str, request: Request) -> JSONResponse:
    job = server_of(request).scheduler.cancel(job_id)
    if job is None:
        raise ServerError(404, f"no job {job_id!r} is queued or running", ErrorType.NOT_FOUND, "job_not_found",
                          "job_id")
    return JSONResponse(job.info().model_dump(mode="json"))
