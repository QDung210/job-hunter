"""Normalized job schema shared by every collector and downstream stage."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


def normalize_company(name: str) -> str:
    n = (name or "").lower().strip()
    n = re.sub(r"[.,]", "", n)
    n = re.sub(r"\b(inc|llc|ltd|corp|corporation|co)\b\.?", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalize_title(title: str) -> str:
    t = (title or "").lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


class Job(BaseModel):
    """Raw job normalized to a common schema, before scoring."""

    source: str
    source_id: str
    title: str
    company: str
    location_raw: Optional[str] = None
    remote: Optional[bool] = None
    url: str
    canonical_url: Optional[str] = None
    description: str = ""
    posted_at: Optional[datetime] = None
    posted_at_confidence: str = "unknown"  # "known" | "unknown"
    salary_raw: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    employment_type: Optional[str] = None

    @property
    def company_normalized(self) -> str:
        return normalize_company(self.company)

    @property
    def title_normalized(self) -> str:
        return normalize_title(self.title)

    @property
    def dedupe_url(self) -> str:
        return self.canonical_url or self.url

    @property
    def full_text(self) -> str:
        return f"{self.title}\n{self.description}"


class ScoredJob(BaseModel):
    """Job plus explainable scoring output — matches the spec's notification schema."""

    job: Job
    score: int
    priority: str
    score_breakdown: dict = Field(default_factory=dict)
    technical_matches: list[str] = Field(default_factory=list)
    transferable_matches: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    hard_requirements_missing: list[str] = Field(default_factory=list)
    experience_required: str = "not specified"
    location_eligible: bool = True
    location_confidence: str = "unknown"  # high | low | unknown
    freshness_confidence: str = "unknown"  # known | unknown
    response_probability: str = "UNKNOWN"  # HIGH | MEDIUM | LOW | UNKNOWN
    reason: str = ""
    recommended_action: str = "REVIEW"
    notify_tier: str = "none"  # immediate | digest | none
    url_status: str = "not_checked"  # ok | stale | unknown | not_checked

    def to_output_dict(self) -> dict:
        j = self.job
        return {
            "score": self.score,
            "priority": self.priority,
            "title": j.title,
            "company": j.company,
            "source": j.source,
            "url": j.dedupe_url,
            "posted_at": j.posted_at.isoformat() if j.posted_at else None,
            "remote": j.remote,
            "location": j.location_raw,
            "salary": j.salary_raw,
            "technical_matches": self.technical_matches,
            "transferable_matches": self.transferable_matches,
            "missing_skills": self.missing_skills,
            "hard_requirements_missing": self.hard_requirements_missing,
            "experience_required": self.experience_required,
            "location_eligible": self.location_eligible,
            "location_confidence": self.location_confidence,
            "freshness_confidence": self.freshness_confidence,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "response_probability": self.response_probability,
            "url_status": self.url_status,
            "score_breakdown": self.score_breakdown,
        }
