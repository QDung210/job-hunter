"""Wraps python-jobspy (LinkedIn/Indeed/Google/Glassdoor/ZipRecruiter/etc).

Each site is scraped independently and wrapped in its own try/except: JobSpy
sites are known to vary wildly in reliability from shared CI IPs (Indeed is
the most stable; LinkedIn/Glassdoor/Google are best-effort and may return
empty/403 on GitHub Actions runners) — one site failing must not drop the rest.
"""
from __future__ import annotations

import logging

from ..models import Job
from .base import BaseCollector
from .util import clean_number, parse_date, strip_html

logger = logging.getLogger(__name__)


class JobSpyCollector(BaseCollector):
    name = "jobspy"

    def __init__(self, cfg: dict, search_queries: list[str], location: str = "Remote"):
        super().__init__(cfg)
        self.search_queries = search_queries
        self.results_wanted = int(self.cfg.get("results_wanted_per_site", 30))
        self.hours_old = int(self.cfg.get("hours_old", 168))
        self.sites = self.cfg.get("sites", ["indeed"])
        self.country_indeed = self.cfg.get("country_indeed", "vietnam")
        self.location = location

    def fetch(self) -> list[Job]:
        try:
            from jobspy import scrape_jobs
        except ImportError as e:
            raise RuntimeError(f"python-jobspy not installed: {e}") from e

        jobs: list[Job] = []
        query = self.search_queries[0] if self.search_queries else "AI Engineer"

        for site in self.sites:
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=query,
                    location=self.location,
                    results_wanted=self.results_wanted,
                    hours_old=self.hours_old,
                    country_indeed=self.country_indeed,
                    verbose=0,
                )
            except Exception as e:  # noqa: BLE001 - one JobSpy site must not drop the rest
                logger.warning("[jobspy:%s] site failed, skipping: %s", site, e)
                continue

            if df is None or df.empty:
                logger.info("[jobspy:%s] 0 jobs", site)
                continue

            count_before = len(jobs)
            for _, row in df.iterrows():
                try:
                    jobs.append(self._to_job(site, row))
                except Exception as e:  # noqa: BLE001
                    logger.debug("[jobspy:%s] skipping malformed row: %s", site, e)
            logger.info("[jobspy:%s] %d jobs", site, len(jobs) - count_before)

        return jobs

    def _to_job(self, site: str, row) -> Job:
        posted_at = parse_date(clean_number(row.get("date_posted")))
        salary_min = clean_number(row.get("min_amount"))
        salary_max = clean_number(row.get("max_amount"))
        currency = row.get("currency") or ""
        salary_raw = f"{salary_min or '?'}–{salary_max or '?'} {currency}".strip() if (salary_min or salary_max) else None
        job_url = str(row.get("job_url") or "")
        job_url_direct = clean_number(row.get("job_url_direct"))
        return Job(
            source=f"jobspy_{site}",
            source_id=job_url or str(row.get("id", "")),
            title=str(row.get("title", "") or ""),
            company=str(row.get("company", "") or "Unknown"),
            location_raw=clean_number(row.get("location")),
            remote=bool(row.get("is_remote")) if clean_number(row.get("is_remote")) is not None else None,
            url=job_url,
            canonical_url=str(job_url_direct) if job_url_direct else job_url,
            description=strip_html(str(clean_number(row.get("description")) or "")),
            posted_at=posted_at,
            posted_at_confidence="known" if posted_at else "unknown",
            salary_raw=salary_raw,
            salary_min=salary_min,
            salary_max=salary_max,
            employment_type=clean_number(row.get("job_type")),
        )
