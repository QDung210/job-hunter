"""Loads config/*.yaml + environment secrets into a single Config object."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"


def _load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    def __init__(self):
        load_dotenv(ROOT_DIR / ".env", override=False)

        self.profile: dict = _load_yaml("profile.yaml")
        self.keywords: dict = _load_yaml("keywords.yaml")
        self.sources: dict = _load_yaml("sources.yaml")
        self.companies: dict = _load_yaml("companies.yaml")

        self.telegram_bot_token: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN") or None
        self.telegram_chat_id: Optional[str] = os.environ.get("TELEGRAM_CHAT_ID") or None

    # -- profile helpers -------------------------------------------------
    @property
    def known_terms(self) -> set[str]:
        return {t.lower() for t in self.profile.get("known_terms", [])}

    @property
    def role_titles(self) -> list[str]:
        return self.profile.get("role_titles", [])

    @property
    def search_queries(self) -> list[str]:
        return self.profile.get("search_queries", [])

    @property
    def candidate_years(self) -> float:
        return float(self.profile.get("experience", {}).get("years", 0))

    @property
    def thresholds(self) -> dict:
        return self.profile.get("thresholds", {"notify": 82, "digest": 75, "hot": 90})

    @property
    def max_age_days(self) -> int:
        return int(self.profile.get("search", {}).get("max_age_days", 14))

    @property
    def seen_jobs_expiry_days(self) -> int:
        return int(self.profile.get("search", {}).get("seen_jobs_expiry_days", 45))

    @property
    def location_rules(self) -> dict:
        return self.profile.get("location_rules", {})

    @property
    def experience_rules(self) -> dict:
        return self.profile.get("experience_rules", {})

    @property
    def url_check_config(self) -> dict:
        return self.profile.get("url_check", {})

    # -- sources -----------------------------------------------------------
    def source_cfg(self, name: str) -> dict:
        return self.sources.get(name, {}) or {}

    def is_enabled(self, name: str) -> bool:
        return bool(self.source_cfg(name).get("enabled", False))

    def source_tier(self, name: str) -> str:
        return self.source_cfg(name).get("tier", "light")

    def enabled_sources(self, tier: str = "all") -> list[str]:
        names = []
        for name, cfg in (self.sources or {}).items():
            if not cfg or not cfg.get("enabled", False):
                continue
            if tier != "all" and cfg.get("tier", "light") != tier:
                continue
            names.append(name)
        return names


_config_singleton: Optional[Config] = None


def get_config() -> Config:
    global _config_singleton
    if _config_singleton is None:
        _config_singleton = Config()
    return _config_singleton
