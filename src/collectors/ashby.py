"""Ashby public job-board posting API — no key needed.
https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
"""
from __future__ import annotations

import logging

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date, strip_html

logger = logging.getLogger(__name__)


class AshbyCollector(BaseCollector):
    name = "ashby"

    def __init__(self, cfg: dict, companies: list[str]):
        super().__init__(cfg)
        self.companies = companies

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        with self.client() as client:
            for slug in self.companies:
                url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
                try:
                    resp = self.get_with_retry(client, url, params={"includeCompensation": "true"})
                except httpx.HTTPError as e:
                    logger.warning("[ashby] %s failed: %s", slug, e)
                    continue
                if resp.status_code == 404:
                    logger.warning("[ashby] board '%s' not found (404) — skipping", slug)
                    continue
                if resp.status_code != 200:
                    logger.warning("[ashby] %s returned %s", slug, resp.status_code)
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    continue
                for item in data.get("jobs", []):
                    try:
                        jobs.append(self._to_job(slug, item))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[ashby] skipping malformed job from %s: %s", slug, e)
        return jobs

    def _to_job(self, slug: str, item: dict) -> Job:
        posted_at = parse_date(item.get("publishedAt"))
        url = item.get("jobUrl") or item.get("applyUrl", "")
        return Job(
            source="ashby",
            source_id=str(item.get("id", "")),
            title=item.get("title", ""),
            company=slug,
            location_raw=item.get("location"),
            remote=bool(item.get("isRemote")),
            url=url,
            canonical_url=item.get("applyUrl") or url,
            description=strip_html(item.get("descriptionHtml") or item.get("descriptionPlain") or ""),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
        )
