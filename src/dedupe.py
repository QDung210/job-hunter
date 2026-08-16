"""Cross-source deduplication against data/seen_jobs.json.

Priority for the canonical URL kept when the same job appears from multiple
sources: direct company career page > direct ATS API (Greenhouse/Lever/Ashby/
Workable/SmartRecruiters) > Wellfound/JobSpy > aggregator (RemoteOK/Remotive/
Arbeitnow/Himalayas/Jobicy/WeWorkRemotely). Collectors set `canonical_url` when
they can see one; dedupe falls back to `url` otherwise.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from rapidfuzz import fuzz

from .models import Job

TRACKING_PARAM_PREFIXES = ("utm_", "gh_src", "ref", "source", "trk", "fbclid", "gclid")

SOURCE_PRIORITY = {
    # lower number = more canonical / preferred when merging duplicates
    "greenhouse": 1, "lever": 1, "ashby": 1, "workable": 1, "smartrecruiters": 1,
    "wellfound": 2, "jobspy_indeed": 2, "jobspy_linkedin": 2, "jobspy_google": 2,
    "jobspy_glassdoor": 2, "jobspy_zip_recruiter": 2,
    "remoteok": 3, "remotive": 3, "arbeitnow": 3, "himalayas": 3, "jobicy": 3,
    "weworkremotely": 3,
}


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = "https"
    netloc = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query)
        if not any(k.lower().startswith(p) for p in TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


class Deduper:
    def __init__(self, seen: dict, fuzzy_threshold: int = 92):
        self.seen = seen
        self.fuzzy_threshold = fuzzy_threshold
        self._by_company: dict[str, list[str]] = defaultdict(list)
        for key, rec in seen.items():
            self._by_company[rec.get("company_normalized", "")].append(key)

    def canonical_key(self, job: Job) -> str:
        return normalize_url(job.dedupe_url)

    def find_duplicate_key(self, job: Job) -> Optional[str]:
        url_key = self.canonical_key(job)
        if url_key in self.seen:
            return url_key

        company = job.company_normalized
        title_n = job.title_normalized
        loc = (job.location_raw or "").strip().lower()
        for key in self._by_company.get(company, []):
            rec = self.seen[key]
            if fuzz.token_sort_ratio(title_n, rec.get("title_normalized", "")) >= self.fuzzy_threshold:
                rec_loc = (rec.get("location") or "").strip().lower()
                if not loc or not rec_loc or loc == rec_loc:
                    return key
        return None

    def is_duplicate(self, job: Job) -> bool:
        return self.find_duplicate_key(job) is not None

    def register(self, job: Job, score: int, notified: bool) -> None:
        key = self.canonical_key(job)
        now = datetime.now(timezone.utc).isoformat()
        existing = self.seen.get(key, {})

        # Prefer keeping the more canonical URL/source if this job was already seen
        # from a lower-priority source.
        existing_priority = SOURCE_PRIORITY.get(existing.get("source", ""), 99)
        new_priority = SOURCE_PRIORITY.get(job.source, 99)
        keep_source = job.source if new_priority <= existing_priority else existing.get("source", job.source)
        keep_url = job.dedupe_url if new_priority <= existing_priority else existing.get("url", job.dedupe_url)

        rec = {
            "first_seen": existing.get("first_seen", now),
            "last_seen": now,
            "source": keep_source,
            "company_normalized": job.company_normalized,
            "title_normalized": job.title_normalized,
            "location": job.location_raw or "",
            "score": score,
            "notified": bool(existing.get("notified")) or notified,
            "url": keep_url,
        }
        self.seen[key] = rec
        self._by_company[job.company_normalized].append(key)

    def was_notified(self, job: Job) -> bool:
        key = self.find_duplicate_key(job)
        if key is None:
            return False
        return bool(self.seen.get(key, {}).get("notified"))
