"""Follow this session's generations, which run in the backend.

Generations no longer block the form: each Generate click is its own job, and
several can run at once. The backend holds the jobs, so leaving the page or
closing the tab never abandons a paid render - this module only decides which
finished runs this session should announce.
"""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

import api

ACTIVE = ("queued", "running")


def track(job: Dict) -> None:
    st.session_state.asset_jobs.append(job['id'])


def my_jobs() -> List[Dict]:
    """This session's tracked jobs, fresh from the backend.

    A job the backend no longer knows means it restarted; it is reported as
    failed rather than tracked forever.
    """
    found = []
    for job_id in st.session_state.asset_jobs:
        try:
            found.append(api.get(f"/jobs/{job_id}"))
        except api.ApiError as exc:
            if exc.status != 404:
                raise
            found.append({'id': job_id, 'label': "A generation", 'status': "failed",
                          'error': str(exc), 'result': None})
    return found


def collect() -> List[Dict]:
    """Move finished jobs into the notices and return the ones still running."""
    running = []
    for job in my_jobs():
        if job['status'] in ACTIVE:
            running.append(job)
        else:
            st.session_state.job_notices.append(job)
    st.session_state.asset_jobs = [job['id'] for job in running]
    return running


def show_notices() -> None:
    """Report every finished job once."""
    for job in st.session_state.job_notices:
        if job['status'] == "failed":
            st.error(f"**{job['label']}** failed: {job['error']}")
            continue
        result = job['result']
        if result.get('warning'):
            st.warning(f"**{job['label']}** - one provider failed: {result['warning']}")
        st.success(f"**{job['label']}** landed in the library.")
        columns = st.columns(6)
        for column, asset in zip(columns, result['assets']):
            column.image(str(api.file_path(asset['path'])), caption=asset['label'], width='stretch')
    st.session_state.job_notices = []
