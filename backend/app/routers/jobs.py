"""Background jobs of every kind: poll these to follow a generation or a search
that was started elsewhere."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException

from app import jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def get_jobs(kind: Optional[str] = None, active: bool = False) -> List[Dict]:
    """Jobs newest first. ``active=true`` keeps only queued and running ones."""
    return [job.to_dict() for job in jobs.list_jobs(kind, active)]


@router.get("/{job_id}")
def get_job(job_id: str) -> Dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job - the server may have restarted.")
    return job.to_dict()
