"""Greenhouse public job-board API — no key needed.
https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
"""
from __future__ import annotations

import logging

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date, strip_html

logger = logging.getLogger(__name__)


class GreenhouseCollector(BaseCollector):
    name = "greenhouse"

    def __init__(self, cfg: dict, companies: list[str]):
        super().__init__(cfg)
        self.companies = companies

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        with self.client() as client:
            for company in self.companies:
                url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
                try:
                    resp = self.get_with_retry(client, url, params={"content": "true"})
                except httpx.HTTPError as e:
                    logger.warning("[greenhouse] %s failed: %s", company, e)
                    continue
                if resp.status_code == 404:
                    logger.warning("[greenhouse] company slug '%s' not found (404) — skipping", company)
                    continue
                if resp.status_code != 200:
                    logger.warning("[greenhouse] %s returned %s", company, resp.status_code)
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("[greenhouse] %s returned invalid JSON", company)
                    continue
                for item in data.get("jobs", []):
                    try:
                        jobs.append(self._to_job(company, item))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[greenhouse] skipping malformed job from %s: %s", company, e)
        return jobs

    def _to_job(self, company: str, item: dict) -> Job:
        loc = (item.get("location") or {}).get("name")
        posted_at = parse_date(item.get("updated_at") or item.get("first_published"))
        remote = bool(loc and "remote" in loc.lower())
        url = item.get("absolute_url", "")
        return Job(
            source="greenhouse",
            source_id=str(item.get("id", "")),
            title=item.get("title", ""),
            company=company,
            location_raw=loc,
            remote=remote,
            url=url,
            canonical_url=url,
            description=strip_html(item.get("content") or ""),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
        )
