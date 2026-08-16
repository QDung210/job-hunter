"""SmartRecruiters public postings API — no key needed.
https://api.smartrecruiters.com/v1/companies/{company_id}/postings

NOTE: some companies disable their public feed on lower plans — a valid
company_id can legitimately return zero postings; that is not an error.
"""
from __future__ import annotations

import logging

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date

logger = logging.getLogger(__name__)


class SmartRecruitersCollector(BaseCollector):
    name = "smartrecruiters"

    def __init__(self, cfg: dict, companies: list[str]):
        super().__init__(cfg)
        self.companies = companies

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        with self.client() as client:
            for company_id in self.companies:
                url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
                try:
                    resp = self.get_with_retry(client, url, params={"limit": 100})
                except httpx.HTTPError as e:
                    logger.warning("[smartrecruiters] %s failed: %s", company_id, e)
                    continue
                if resp.status_code == 404:
                    logger.warning("[smartrecruiters] company '%s' not found (404) — skipping", company_id)
                    continue
                if resp.status_code != 200:
                    logger.warning("[smartrecruiters] %s returned %s", company_id, resp.status_code)
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    continue
                for item in data.get("content", []):
                    try:
                        jobs.append(self._to_job(company_id, item))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[smartrecruiters] skipping malformed job from %s: %s", company_id, e)
        return jobs

    def _to_job(self, company_id: str, item: dict) -> Job:
        loc = item.get("location") or {}
        loc_str = ", ".join(filter(None, [loc.get("city"), loc.get("country")])) or None
        posted_at = parse_date(item.get("releasedDate") or item.get("createdOn"))
        company_name = (item.get("company") or {}).get("name", company_id)
        posting_id = item.get("id", "")
        url = item.get("applyUrl") or f"https://jobs.smartrecruiters.com/{company_id}/{posting_id}"
        return Job(
            source="smartrecruiters",
            source_id=str(posting_id),
            title=item.get("name", ""),
            company=company_name,
            location_raw=loc_str,
            remote=bool(loc.get("remote")),
            url=url,
            canonical_url=url,
            description=item.get("name", ""),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
        )
