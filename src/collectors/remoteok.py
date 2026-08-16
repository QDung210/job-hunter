"""RemoteOK public API — no key, but requires a realistic browser User-Agent
or it returns 403. https://remoteok.com/api
"""
from __future__ import annotations

import logging

import httpx

from ..models import Job
from .base import BaseCollector
from .util import parse_date, strip_html

logger = logging.getLogger(__name__)


class RemoteOkCollector(BaseCollector):
    name = "remoteok"

    def fetch(self) -> list[Job]:
        with self.client() as client:
            try:
                resp = self.get_with_retry(client, "https://remoteok.com/api")
            except httpx.HTTPError as e:
                raise RuntimeError(f"remoteok request failed: {e}") from e
            if resp.status_code != 200:
                raise RuntimeError(f"remoteok returned {resp.status_code}")
            try:
                data = resp.json()
            except ValueError as e:
                raise RuntimeError(f"remoteok returned invalid JSON: {e}") from e

        jobs: list[Job] = []
        for item in data:
            # first element of the response is a legacy/metadata object, not a job
            if not isinstance(item, dict) or "id" not in item or "position" not in item:
                continue
            try:
                jobs.append(self._to_job(item))
            except Exception as e:  # noqa: BLE001
                logger.debug("[remoteok] skipping malformed job: %s", e)
        return jobs

    def _to_job(self, item: dict) -> Job:
        posted_at = parse_date(item.get("date"))
        tags = item.get("tags") or []
        description = strip_html(item.get("description") or "")
        if tags:
            description = f"{description} {' '.join(tags)}"
        salary_min = item.get("salary_min") or None
        salary_max = item.get("salary_max") or None
        salary_raw = f"${salary_min or '?'}–${salary_max or '?'}" if (salary_min or salary_max) else None
        url = item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id')}"
        return Job(
            source="remoteok",
            source_id=str(item.get("id")),
            title=item.get("position", ""),
            company=item.get("company", ""),
            location_raw=item.get("location") or "Remote",
            remote=True,
            url=url,
            canonical_url=item.get("apply_url") or url,
            description=description,
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
            salary_raw=salary_raw,
            salary_min=salary_min,
            salary_max=salary_max,
        )
