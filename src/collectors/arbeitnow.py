"""Arbeitnow public job-board API — no key needed, paginated.
https://www.arbeitnow.com/api/job-board-api
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date, strip_html

logger = logging.getLogger(__name__)


class ArbeitnowCollector(BaseCollector):
    name = "arbeitnow"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.max_pages = int(self.cfg.get("max_pages", 3))

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        url = "https://www.arbeitnow.com/api/job-board-api"
        page = 0
        with self.client() as client:
            while url and page < self.max_pages:
                try:
                    resp = self.get_with_retry(client, url)
                except httpx.HTTPError as e:
                    logger.warning("[arbeitnow] page %s failed: %s", page, e)
                    break
                if resp.status_code != 200:
                    logger.warning("[arbeitnow] page %s returned %s", page, resp.status_code)
                    break
                try:
                    data = resp.json()
                except ValueError:
                    break
                for item in data.get("data", []):
                    try:
                        jobs.append(self._to_job(item))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[arbeitnow] skipping malformed job: %s", e)
                url = (data.get("links") or {}).get("next") or None
                page += 1
        return jobs

    def _to_job(self, item: dict) -> Job:
        posted_at = None
        ts = item.get("created_at")
        if ts:
            try:
                posted_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (ValueError, TypeError, OSError, OverflowError):
                posted_at = parse_date(ts)
        tags = item.get("tags") or []
        description = strip_html(item.get("description") or "")
        if tags:
            description = f"{description} {' '.join(tags)}"
        return Job(
            source="arbeitnow",
            source_id=str(item.get("slug", "")),
            title=item.get("title", ""),
            company=item.get("company_name", ""),
            location_raw=item.get("location"),
            remote=bool(item.get("remote")),
            url=item.get("url", ""),
            canonical_url=item.get("url"),
            description=description,
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
            employment_type=", ".join(item.get("job_types") or []) or None,
        )
