"""BaseCollector: every source is independent — a failure here must never take
down the rest of the pipeline. `run()` is the only entrypoint main.py calls;
it isolates exceptions and logs a one-line summary per source."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class BaseCollector(ABC):
    name: str = "base"

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}
        self.timeout = float(self.cfg.get("timeout_seconds", 10))
        self.retries = int(self.cfg.get("retries", 2))

    @abstractmethod
    def fetch(self) -> list:
        """Return a list of models.Job. May raise — run() isolates it."""

    def run(self) -> list:
        try:
            jobs = self.fetch()
            logger.info("[%s] %d jobs", self.name, len(jobs))
            return jobs
        except Exception as e:  # noqa: BLE001 - one bad source must never kill the run
            logger.warning("[%s] collector FAILED: %s", self.name, e)
            return []

    def client(self, headers: dict | None = None) -> httpx.Client:
        h = {"User-Agent": self.cfg.get("user_agent", DEFAULT_USER_AGENT)}
        if headers:
            h.update(headers)
        return httpx.Client(timeout=self.timeout, headers=h, follow_redirects=True)

    def get_with_retry(self, client: httpx.Client, url: str, **kwargs) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = client.get(url, **kwargs)
                if resp.status_code >= 500 and attempt < self.retries:
                    last_exc = RuntimeError(f"{url} returned {resp.status_code}")
                    continue
                return resp
            except httpx.HTTPError as e:
                last_exc = e
        assert last_exc is not None
        raise last_exc
