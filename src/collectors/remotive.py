"""Remotive public API — no key needed.
https://remotive.com/api/remote-jobs?search=<term>
"""
from __future__ import annotations

import logging

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date, strip_html

logger = logging.getLogger(__name__)


class RemotiveCollector(BaseCollector):
    name = "remotive"

    def __init__(self, cfg: dict, search_queries: list[str]):
        super().__init__(cfg)
        self.search_queries = search_queries[:8]  # cap fan-out to keep the run fast

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        seen_ids: set = set()
        with self.client() as client:
            for q in self.search_queries:
                try:
                    resp = self.get_with_retry(client, "https://remotive.com/api/remote-jobs", params={"search": q})
                except httpx.HTTPError as e:
                    logger.warning("[remotive] query '%s' failed: %s", q, e)
                    continue
                if resp.status_code != 200:
                    logger.warning("[remotive] query '%s' returned %s", q, resp.status_code)
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    continue
                for item in data.get("jobs", []):
                    jid = item.get("id")
                    if jid in seen_ids:
                        continue
                    seen_ids.add(jid)
                    try:
                        jobs.append(self._to_job(item))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[remotive] skipping malformed job: %s", e)
        return jobs

    def _to_job(self, item: dict) -> Job:
        posted_at = parse_date(item.get("publication_date"))
        return Job(
            source="remotive",
            source_id=str(item.get("id", "")),
            title=item.get("title", ""),
            company=item.get("company_name", ""),
            location_raw=item.get("candidate_required_location"),
            remote=True,
            url=item.get("url", ""),
            canonical_url=item.get("url"),
            description=strip_html(item.get("description") or ""),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
            salary_raw=item.get("salary") or None,
            employment_type=item.get("job_type"),
        )
