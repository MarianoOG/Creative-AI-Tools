"""Background jobs that outlive the request that started them.

One click can spend real credits (an image render), so that work never runs
inside a request. It goes to a thread pool
instead: once :func:`submit` returns, the job runs to the end and writes its
result to disk whether or not anyone is still polling for it.

Each kind of job gets its own pool, and the pool size is the concurrency cap
for that kind:

- ``asset``     - 4 workers. Several generations can run at once, but not an
  unbounded number of paid calls.

The pool threads are non-daemon on purpose - shutting the server down waits for
an in-flight render rather than discarding one that has already been paid for.
This registry is in-process memory, which is why the backend must run as a
single worker process.
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

#: A job body. It receives a ``progress`` callback for human-readable steps and
#: returns a JSON-serialisable result.
JobFn = Callable[[Callable[[str], None]], Any]

_POOLS: Dict[str, ThreadPoolExecutor] = {
    "asset": ThreadPoolExecutor(max_workers=4, thread_name_prefix="asset"),
}

#: Finished jobs kept for polling. Older ones are dropped first.
_MAX_FINISHED = 200

_LOCK = threading.Lock()
_REGISTRY: Dict[str, "Job"] = {}


@dataclass
class Job:
    """One submitted job. The future is the source of truth for its outcome."""

    id: str
    kind: str
    label: str
    future: Future
    #: The world an asset job writes into, so that world can be held against
    #: rename and delete while the job runs. ``None`` for every other kind.
    world: Optional[str] = None
    progress: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def done(self) -> bool:
        return self.future.done()

    @property
    def status(self) -> str:
        if not self.future.done():
            return "running" if self.future.running() else "queued"
        return "failed" if self.future.exception() is not None else "done"

    def to_dict(self) -> Dict[str, Any]:
        status = self.status
        exc = self.future.exception() if status == "failed" else None
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "world": self.world,
            "status": status,
            "progress": list(self.progress),
            "created_at": self.created_at,
            "result": self.future.result() if status == "done" else None,
            "error": str(exc) if exc is not None else None,
        }


def _prune() -> None:
    """Drop the oldest finished jobs beyond :data:`_MAX_FINISHED`. Caller holds the lock."""
    finished = sorted(
        (job for job in _REGISTRY.values() if job.done()), key=lambda job: job.created_at
    )
    for job in finished[: max(0, len(finished) - _MAX_FINISHED)]:
        _REGISTRY.pop(job.id, None)


def submit(kind: str, label: str, fn: JobFn, world: Optional[str] = None) -> Job:
    """Start ``fn`` on the ``kind`` pool and return its job."""
    job_id = uuid.uuid4().hex
    progress: List[str] = []
    future = _POOLS[kind].submit(fn, progress.append)
    job = Job(id=job_id, kind=kind, label=label, future=future, world=world, progress=progress)
    with _LOCK:
        _REGISTRY[job_id] = job
        _prune()
    return job


def get(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _REGISTRY.get(job_id)


def list_jobs(kind: Optional[str] = None, active: bool = False) -> List[Job]:
    """Jobs newest first, optionally only one kind and only unfinished ones."""
    with _LOCK:
        jobs = list(_REGISTRY.values())
    return sorted(
        (
            job
            for job in jobs
            if (kind is None or job.kind == kind) and not (active and job.done())
        ),
        key=lambda job: job.created_at,
        reverse=True,
    )


def busy_worlds() -> set[str]:
    """Worlds an unfinished asset job is about to write into."""
    return {job.world for job in list_jobs("asset", active=True) if job.world}


def shutdown() -> None:
    """Wait for every in-flight job. Called once, when the server stops."""
    for pool in _POOLS.values():
        pool.shutdown(wait=True)
