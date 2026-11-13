"""Concurrent classification of items and the output records."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic_ai.exceptions import ModelConnectionError, ModelRateLimitError

from .backends import Result
from .items import Item
from .questions import QuestionError, Questions

# Request failures worth a sequential retry: a rate limit (HTTP 429) and a
# connection error. Any other failure (a bad response, an invalid question)
# is not retried.
RETRYABLE = (ModelRateLimitError, ModelConnectionError)


@dataclass(frozen=True)
class Outcome:
    item: Item
    result: Result | None
    error: str | None
    timestamp: str
    retryable: bool = False


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def classify_one(backend, item: Item, questions: Questions) -> Outcome:
    """One item; any exception becomes the outcome's `error`, retryable when it or its
    cause (`ai_models.errors.explained` wraps a connection error) is in RETRYABLE."""
    try:
        if not item.text.strip():
            raise QuestionError("empty text")
        result = backend.classify(item.text, questions)
    except Exception as e:  # noqa: BLE001 - one failed item must not stop the run
        return Outcome(item, None, f"{type(e).__name__}: {e}", now(),
                       isinstance(e, RETRYABLE) or isinstance(e.__cause__, RETRYABLE))
    return Outcome(item, result, None, now())


def retryable(outcome: Outcome) -> bool:
    """A failure that a sequential retry might clear (rate limit or connection)."""
    return outcome.error is not None and outcome.retryable


def run_with_retry(backend, items: list[Item], questions: Questions, concurrency: int = 8,
                   retry_failed: int = 0,
                   on_outcome: Callable[[Outcome], None] | None = None) -> list[Outcome]:
    """Outcomes in input order. Items run `concurrency` at a time; after that
    pass, items that failed with a rate-limit (429) or connection error are
    retried sequentially, up to `retry_failed` more passes, until none remain
    or the passes run out. Items failing for other reasons are left as they
    are. `on_outcome` is called in the calling thread with each outcome as it
    arrives, retries included, so the caller can write it at once."""
    backend.check(questions)
    emit = on_outcome or (lambda o: None)
    outcomes: list[Outcome | None] = [None] * len(items)
    pool = ThreadPoolExecutor(max_workers=max(1, concurrency))
    futures = {pool.submit(classify_one, backend, it, questions): n for n, it in enumerate(items)}
    try:
        for fut in as_completed(futures):
            outcomes[futures[fut]] = o = fut.result()
            emit(o)
    except BaseException:
        # An interrupt: drop the queued items, wait for the requests in flight
        # and pass on the outcomes nobody has seen yet, so they are kept.
        pool.shutdown(wait=True, cancel_futures=True)
        for fut, n in futures.items():
            if outcomes[n] is None and fut.done() and not fut.cancelled() and fut.exception() is None:
                emit(fut.result())
        raise
    pool.shutdown()
    for _ in range(max(0, retry_failed)):
        pending = [n for n, o in enumerate(outcomes) if retryable(o)]
        if not pending:
            break
        for n in pending:
            outcomes[n] = o = classify_one(backend, outcomes[n].item, questions)
            emit(o)
    return outcomes


def record(outcome: Outcome, backend_name: str, model: str, questions: Questions) -> dict[str, Any]:
    """The output line of one item. `top` and `p_top` only for one question."""
    r = outcome.result
    rec: dict[str, Any] = {
        "id": outcome.item.id,
        "backend": backend_name,
        "model": (r.model if r and r.model else model),
        "request_id": r.request_id if r else None,
        "timestamp": outcome.timestamp,
    }
    if r is None:
        rec["error"] = outcome.error
        return rec
    rec["answers"] = r.answers
    if len(questions) == 1:
        [qid] = questions
        rec["top"] = r.top[qid]
        rec["p_top"] = r.p_top[qid]
    return rec
