"""Workable public widget API — no key needed.
https://apply.workable.com/api/v1/widget/accounts/{account}?details=true
"""
from __future__ import annotations

import logging

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date, strip_html

logger = logging.getLogger(__name__)


class WorkableCollector(BaseCollector):
    name = "workable"

    def __init__(self, cfg: dict, companies: list[str]):
        super().__init__(cfg)
        self.companies = companies

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        with self.client() as client:
            for account in self.companies:
                url = f"https://apply.workable.com/api/v1/widget/accounts/{account}"
                try:
                    resp = self.get_with_retry(client, url, params={"details": "true"})
                except httpx.HTTPError as e:
                    logger.warning("[workable] %s failed: %s", account, e)
                    continue
                if resp.status_code == 404:
                    logger.warning("[workable] account '%s' not found (404) — skipping", account)
                    continue
                if resp.status_code != 200:
                    logger.warning("[workable] %s returned %s", account, resp.status_code)
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    continue
                for item in data.get("jobs", []):
                    try:
                        jobs.append(self._to_job(account, item))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[workable] skipping malformed job from %s: %s", account, e)
        return jobs

    def _to_job(self, account: str, item: dict) -> Job:
        posted_at = parse_date(item.get("published_on") or item.get("created_at"))
        loc = ", ".join(filter(None, [item.get("city"), item.get("country")])) or item.get("location")
        remote = bool(item.get("telecommuting")) or bool(item.get("remote"))
        url = item.get("url") or item.get("shortlink", "")
        return Job(
            source="workable",
            source_id=str(item.get("id") or item.get("shortcode", "")),
            title=item.get("title", ""),
            company=account,
            location_raw=loc,
            remote=remote,
            url=url,
            canonical_url=url,
            description=strip_html(item.get("description") or ""),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
            employment_type=item.get("employment_type"),
        )
