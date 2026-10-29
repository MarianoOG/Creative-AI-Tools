"""The only module that talks to the backend.

The backend owns every write. This app only reads the shared data folder, to
show and download the files whose paths the API hands back - paths that are
always relative to that folder, so each service can mount it wherever it likes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")

#: Defaults to ``world-builder/data``, the same folder a local backend writes to.
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

#: Generous, because a generate request carries the uploaded reference images.
TIMEOUT = 60


class ApiError(Exception):
    """A request the backend refused or could not answer. ``str()`` is the reason."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status


def _detail(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        return response.text or response.reason
    if isinstance(detail, list):  # FastAPI validation errors
        return "; ".join(str(error.get("msg", error)) for error in detail)
    return str(detail)


def request(method: str, path: str, **kwargs: Any) -> Any:
    """Call the backend and return the decoded JSON body, or ``None`` if empty."""
    try:
        response = requests.request(method, f"{BACKEND_URL}{path}", timeout=TIMEOUT, **kwargs)
    except requests.ConnectionError as exc:
        raise ApiError(0, f"The backend is not reachable at {BACKEND_URL}.") from exc
    if response.status_code >= 400:
        raise ApiError(response.status_code, _detail(response))
    return response.json() if response.content else None


def get(path: str, **params: Any) -> Any:
    return request("GET", path, params={k: v for k, v in params.items() if v is not None})


def post(path: str, json: Optional[Dict] = None, **kwargs: Any) -> Any:
    return request("POST", path, json=json, **kwargs)


def patch(path: str, json: Dict) -> Any:
    return request("PATCH", path, json=json)


def delete(path: str, **params: Any) -> Any:
    return request("DELETE", path, params=params)


def file_path(relative: str) -> Path:
    """Where a path from the API lives on this service's read-only mount."""
    return DATA_DIR / relative


@st.cache_data(ttl=300, show_spinner=False)
def options(section: str) -> Dict[str, List]:
    """Form options (styles, aspect ratios, ...). They only change with a deploy."""
    return get(f"/{section}/options")
