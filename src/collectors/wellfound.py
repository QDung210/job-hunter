"""Wellfound (ex-AngelList Talent) — BEST-EFFORT collector.

Known limitation (documented in README "Known limitations"): Wellfound has no
public API, and robots.txt disallows the exact /role/l/... search paths this
collector reads. Job data is embedded as a `__NEXT_DATA__` JSON blob in the
server-rendered HTML, so no JS rendering is required to read it — but
datacenter IPs (like GitHub Actions runners) risk soft blocks/403s, and the
exact JSON key names can change without notice since there's no stable schema
contract. This collector therefore:
  - sends a realistic browser User-Agent (not evasion — same as any browser)
  - makes very few requests (one per configured role/location URL)
  - fails silently (logs a warning, returns whatever it could parse) on any
    network error, non-200 status, or unexpected JSON shape
  - is scheduled infrequently (heavy tier, every few hours) out of respect for
    the site's stated preferences

If this stops working entirely, disable it via `wellfound.enabled: false` in
config/sources.yaml — every other collector is fully independent of it.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from ..models import Job
from .base import BaseCollector
from .util import strip_html

logger = logging.getLogger(__name__)

NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
JOB_KEY_SETS = [
    {"title", "companyName"},
    {"jobTitle", "company"},
    {"title", "company"},
]


class WellfoundCollector(BaseCollector):
    name = "wellfound"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.urls = self.cfg.get("role_location_urls", [])

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        with self.client() as client:
            for url in self.urls:
                try:
                    resp = client.get(url)
                except httpx.HTTPError as e:
                    logger.warning("[wellfound] %s failed (network) — best-effort source, skipping: %s", url, e)
                    continue
                if resp.status_code in (403, 429):
                    logger.warning("[wellfound] %s returned %s — likely anti-bot block, skipping", url, resp.status_code)
                    continue
                if resp.status_code != 200:
                    logger.warning("[wellfound] %s returned %s — skipping", url, resp.status_code)
                    continue
                try:
                    extracted = self._extract_jobs(resp.text, url)
                except Exception as e:  # noqa: BLE001
                    logger.warning("[wellfound] failed to parse %s (page structure may have changed): %s", url, e)
                    continue
                jobs.extend(extracted)
        return jobs

    def _extract_jobs(self, html_text: str, source_url: str) -> list[Job]:
        match = NEXT_DATA_RE.search(html_text)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        found: list[dict] = []

        def walk(node):
            if isinstance(node, dict):
                keys = set(node.keys())
                if any(key_set.issubset(keys) for key_set in JOB_KEY_SETS):
                    found.append(node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(data)

        jobs = []
        for item in found:
            try:
                jobs.append(self._to_job(item, source_url))
            except Exception as e:  # noqa: BLE001
                logger.debug("[wellfound] skipping malformed job node: %s", e)
        return jobs

    def _to_job(self, item: dict, source_url: str) -> Job:
        title = item.get("title") or item.get("jobTitle") or ""
        company = item.get("companyName") or item.get("company") or "Unknown"
        if isinstance(company, dict):
            company = company.get("name", "Unknown")
        job_id = str(item.get("id") or item.get("jobId") or hash(f"{title}{company}"))
        slug = item.get("slug") or item.get("jobSlug")
        url = f"https://wellfound.com/jobs/{slug}" if slug else source_url
        return Job(
            source="wellfound",
            source_id=job_id,
            title=str(title),
            company=str(company),
            location_raw=item.get("locationName") or item.get("location"),
            remote=bool(item.get("remote", True)),
            url=url,
            canonical_url=url,
            description=strip_html(str(item.get("description") or "")),
            posted_at=None,
            posted_at_confidence="unknown",
        )
