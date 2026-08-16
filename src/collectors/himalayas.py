"""Himalayas public jobs API — no key needed, max 20 results/page.
https://himalayas.app/jobs/api
"""
from __future__ import annotations

import logging

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date, strip_html

logger = logging.getLogger(__name__)


class HimalayasCollector(BaseCollector):
    name = "himalayas"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.max_pages = int(self.cfg.get("max_pages", 3))

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        limit = 20
        offset = 0
        with self.client() as client:
            for _ in range(self.max_pages):
                try:
                    resp = self.get_with_retry(
                        client, "https://himalayas.app/jobs/api", params={"limit": limit, "offset": offset}
                    )
                except httpx.HTTPError as e:
                    logger.warning("[himalayas] offset %s failed: %s", offset, e)
                    break
                if resp.status_code == 429:
                    logger.warning("[himalayas] rate limited (429) at offset %s — stopping early", offset)
                    break
                if resp.status_code != 200:
                    logger.warning("[himalayas] offset %s returned %s", offset, resp.status_code)
                    break
                try:
                    data = resp.json()
                except ValueError:
                    break
                items = data.get("jobs") or data.get("data") or []
                if not items:
                    break
                for item in items:
                    try:
                        jobs.append(self._to_job(item))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[himalayas] skipping malformed job: %s", e)
                offset += limit
        return jobs

    def _to_job(self, item: dict) -> Job:
        posted_at = parse_date(item.get("pubDate"))
        salary_min = item.get("minSalary") or item.get("salaryMin")
        salary_max = item.get("maxSalary") or item.get("salaryMax")
        salary_raw = f"${salary_min or '?'}–${salary_max or '?'}" if (salary_min or salary_max) else None
        location_raw = item.get("locationRestrictions") or ("Worldwide" if item.get("worldwide") else None)
        url = item.get("applicationLink") or item.get("guid", "")
        return Job(
            source="himalayas",
            source_id=str(item.get("guid") or item.get("id", "")),
            title=item.get("title", ""),
            company=item.get("companyName", ""),
            location_raw=location_raw,
            remote=True,
            url=url,
            canonical_url=item.get("applicationLink"),
            description=strip_html(item.get("excerpt") or item.get("description") or ""),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
            salary_raw=salary_raw,
            salary_min=salary_min,
            salary_max=salary_max,
        )
