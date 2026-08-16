"""Lever public postings API — no key needed.
https://api.lever.co/v0/postings/{company}?mode=json
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..models import Job
from .base import BaseCollector
from .util import strip_html

logger = logging.getLogger(__name__)


class LeverCollector(BaseCollector):
    name = "lever"

    def __init__(self, cfg: dict, companies: list[str]):
        super().__init__(cfg)
        self.companies = companies

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        with self.client() as client:
            for company in self.companies:
                url = f"https://api.lever.co/v0/postings/{company}"
                try:
                    resp = self.get_with_retry(client, url, params={"mode": "json"})
                except httpx.HTTPError as e:
                    logger.warning("[lever] %s failed: %s", company, e)
                    continue
                if resp.status_code == 404:
                    logger.warning("[lever] company '%s' not found (404) — skipping", company)
                    continue
                if resp.status_code != 200:
                    logger.warning("[lever] %s returned %s", company, resp.status_code)
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    continue
                if not isinstance(data, list):
                    continue
                for item in data:
                    try:
                        jobs.append(self._to_job(company, item))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[lever] skipping malformed job from %s: %s", company, e)
        return jobs

    def _to_job(self, company: str, item: dict) -> Job:
        categories = item.get("categories") or {}
        loc = categories.get("location")
        posted_at = None
        ts = item.get("createdAt")
        if ts:
            try:
                posted_at = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
            except (ValueError, TypeError, OSError, OverflowError):
                posted_at = None
        remote = bool(loc and "remote" in loc.lower()) or item.get("workplaceType") == "remote"
        description = strip_html(f"{item.get('description', '')} {item.get('descriptionPlain', '')}")
        url = item.get("hostedUrl", "")
        return Job(
            source="lever",
            source_id=str(item.get("id", "")),
            title=item.get("text", ""),
            company=company,
            location_raw=loc,
            remote=remote,
            url=url,
            canonical_url=item.get("applyUrl") or url,
            description=description,
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
        )
