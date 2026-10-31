"""What every router shares: turning the library's errors into HTTP ones."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from fastapi import HTTPException

from app.assets.worlds import list_worlds


def call(fn: Callable, *args, **kwargs):
    """Run ``fn``, answering 400 with the reason when it refuses (raises ``ValueError``)."""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def check_world(world: str) -> None:
    if world not in list_worlds():
        raise HTTPException(404, f"no world called {world!r}")


@contextmanager
def provider_errors(provider: str) -> Iterator[None]:
    """Answer 502 with the reason when a render fails, whatever the provider raised."""
    try:
        yield
    except Exception as exc:
        raise HTTPException(502, f"{provider}: {exc}") from exc
