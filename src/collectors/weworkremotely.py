"""We Work Remotely — public RSS feeds, no auth needed."""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone

import feedparser
import httpx

from ..models import Job
from .base import BaseCollector
from .util import strip_html

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = ["https://weworkremotely.com/remote-jobs.rss"]


class WeWorkRemotelyCollector(BaseCollector):
    name = "weworkremotely"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.feeds = self.cfg.get("feeds") or DEFAULT_FEEDS

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        with self.client() as client:
            for feed_url in self.feeds:
                try:
                    resp = self.get_with_retry(client, feed_url)
                except httpx.HTTPError as e:
                    logger.warning("[weworkremotely] feed %s failed: %s", feed_url, e)
                    continue
                if resp.status_code != 200:
                    logger.warning("[weworkremotely] feed %s returned %s", feed_url, resp.status_code)
                    continue
                parsed = feedparser.parse(resp.text)
                for entry in parsed.entries:
                    try:
                        jobs.append(self._to_job(entry))
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[weworkremotely] skipping malformed entry: %s", e)
        return jobs

    def _to_job(self, entry) -> Job:
        posted_at = None
        published_parsed = getattr(entry, "published_parsed", None)
        if published_parsed:
            posted_at = datetime.fromtimestamp(calendar.timegm(published_parsed), tz=timezone.utc)

        title_raw = entry.get("title", "")
        company, sep, title = title_raw.partition(":")
        if not sep:
            title, company = title_raw, ""

        link = entry.get("link", "")
        return Job(
            source="weworkremotely",
            source_id=entry.get("id", link),
            title=title.strip() or title_raw,
            company=company.strip() or "Unknown",
            location_raw="Remote",
            remote=True,
            url=link,
            canonical_url=link,
            description=strip_html(entry.get("summary") or ""),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
        )
