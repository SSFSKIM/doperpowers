"""Download links for generated files (print view today; the CSV export's
jobs from M3 on).

A job owns exactly one stored file: `ExportJob.file_key` is a single object
key, the emailed link and the UI's toast point at that one file, and the
signed URL expires after 24 hours. A job that produced several files would
need a second table and the toast's rework, which ticket #212 tracks and
nobody has scheduled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from tally.storage import sign_url

LINK_TTL = timedelta(hours=24)
MAX_OBJECT_BYTES = 5 * 1024**3  # the bucket's single-object limit is 5 GB


@dataclass
class ExportJob:
    id: int
    account_id: int
    report_id: int
    state: str              # queued | running | done | failed
    file_key: str | None    # one object per job
    created_at: datetime
    error: str | None = None


def download_link(job: ExportJob) -> str:
    if job.state != "done" or job.file_key is None:
        raise ValueError(f"job {job.id} has no file yet")
    return sign_url(job.file_key, expires_in=LINK_TTL)
