"""Lightweight dead-job detection: HTTP 404/410 plus common "job closed" phrases.

Deliberately conservative: any network error, timeout, or anti-bot-looking
response (e.g. a 403 from a WAF) resolves to "unknown", never "stale" — we'd
rather show a live-but-unverifiable job than hide a real one on a false positive.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

DEAD_STATUS_CODES = {404, 410}

CLOSED_PHRASES = [
    "job no longer available",
    "no longer accepting applications",
    "position has been filled",
    "this job is closed",
    "job not found",
    "application closed",
    "posting has expired",
    "this position is no longer",
    "job posting is no longer active",
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

MAX_BODY_BYTES = 200_000  # cap how much of a GET fallback body we read


def check_url(url: str, timeout_seconds: float = 6.0) -> str:
    """Returns 'ok' | 'stale' | 'unknown'.

    HEAD is tried first as a cheap way to catch an obvious 404/410 without
    downloading a body. HEAD responses never carry a body though, so phrase
    detection ("no longer accepting applications" etc.) requires a GET —
    we always follow up with one unless HEAD already proved the job is dead.
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True, headers=headers) as client:
            try:
                head_resp = client.head(url)
                if head_resp.status_code in DEAD_STATUS_CODES:
                    return "stale"
            except httpx.HTTPError:
                pass  # some job boards don't support HEAD — fall through to GET

            resp = client.get(url)
            if resp.status_code in DEAD_STATUS_CODES:
                return "stale"
            if resp.status_code in (403, 429):
                return "unknown"  # likely anti-bot, not a real dead-job signal
            if resp.status_code >= 400:
                return "unknown"

            body = resp.text[:MAX_BODY_BYTES].lower() if resp.text else ""
            if any(phrase in body for phrase in CLOSED_PHRASES):
                return "stale"
            return "ok"
    except httpx.HTTPError as e:
        logger.debug("URL check failed for %s: %s", url, e)
        return "unknown"
