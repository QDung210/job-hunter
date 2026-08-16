"""Jobicy public API — no key needed. Docs ask for at most hourly polling.
https://jobicy.com/api/v2/remote-jobs
"""
from __future__ import annotations

import logging

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date, strip_html

logger = logging.getLogger(__name__)


class JobicyCollector(BaseCollector):
    name = "jobicy"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.count = int(self.cfg.get("count", 100))

    def fetch(self) -> list[Job]:
        with self.client() as client:
            try:
                resp = self.get_with_retry(
                    client, "https://jobicy.com/api/v2/remote-jobs", params={"count": self.count}
                )
            except httpx.HTTPError as e:
                raise RuntimeError(f"jobicy request failed: {e}") from e
            if resp.status_code != 200:
                raise RuntimeError(f"jobicy returned {resp.status_code}")
            try:
                data = resp.json()
            except ValueError as e:
                raise RuntimeError(f"jobicy returned invalid JSON: {e}") from e

        jobs: list[Job] = []
        for item in data.get("jobs", []):
            try:
                jobs.append(self._to_job(item))
            except Exception as e:  # noqa: BLE001
                logger.debug("[jobicy] skipping malformed job: %s", e)
        return jobs

    def _to_job(self, item: dict) -> Job:
        posted_at = parse_date(item.get("pubDate"))
        salary_min = item.get("annualSalaryMin")
        salary_max = item.get("annualSalaryMax")
        salary_raw = f"${salary_min or '?'}–${salary_max or '?'}" if (salary_min or salary_max) else None
        return Job(
            source="jobicy",
            source_id=str(item.get("id", "")),
            title=item.get("jobTitle", ""),
            company=item.get("companyName", ""),
            location_raw=item.get("jobGeo"),
            remote=True,
            url=item.get("url", ""),
            canonical_url=item.get("url"),
            description=strip_html(item.get("jobExcerpt") or item.get("jobDescription") or ""),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
            salary_raw=salary_raw,
            salary_min=salary_min,
            salary_max=salary_max,
        )
