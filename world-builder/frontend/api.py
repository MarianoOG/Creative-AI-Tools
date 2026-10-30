"""The only module that talks to the backend.

The frontend never writes to the data folder: it only opens the files whose
paths (relative to that folder) the API returns.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")

#: Defaults to ``data/`` at the repository root, where a local backend writes.
DATA_DIR = Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parents[2] / "data")

#: Generous: a generate request waits for the image renders, which can take minutes.
TIMEOUT = 600


class ApiError(Exception):
    """A request the backend refused or could not answer. ``str()`` is the reason."""


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
        raise ApiError(f"The backend is not reachable at {BACKEND_URL}.") from exc
    if response.status_code >= 400:
        raise ApiError(_detail(response))
    return response.json() if response.content else None


def get(path: str, **params: Any) -> Any:
    return request("GET", path, params={k: v for k, v in params.items() if v is not None})


def post(path: str, json: Optional[Dict] = None, **kwargs: Any) -> Any:
    return request("POST", path, json=json, **kwargs)


def patch(path: str, json: Dict) -> Any:
    return request("PATCH", path, json=json)


def put(path: str, json: Dict) -> Any:
    return request("PUT", path, json=json)


def delete(path: str, **params: Any) -> Any:
    return request("DELETE", path, params=params)


def file_path(relative: str) -> Path:
    """Where a path from the API lives on this service's mount."""
    return DATA_DIR / relative


@st.cache_data(ttl=300, show_spinner=False)
def options() -> Dict[str, List]:
    """The form options (asset types, style presets, aspect ratios, ...)."""
    return get("/assets/options")
