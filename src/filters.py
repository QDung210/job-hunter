"""Hard eligibility filters: location reject-list and experience/YOE parsing.

Design intent (per spec):
  - Only reject on EXPLICIT deny phrases (US citizens only, etc). Ambiguous
    location text is NEVER auto-rejected — it's passed through with
    location_confidence="low" so the human can decide.
  - Distinguish "N+ years required" (full penalty) from "N+ years preferred"
    (reduced penalty) rather than treating them the same.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

REQUIRED_MARKERS = ["required", "must have", "minimum", "at least"]
PREFERRED_MARKERS = ["preferred", "nice to have", "nice-to-have", "a plus", "bonus", "ideally"]

YEARS_PATTERN = re.compile(
    r"(\d{1,2})\s*(?:\+|-)?\s*(?:to\s*\d{1,2}\s*)?\+?\s*years?", re.IGNORECASE
)
CONTEXT_WINDOW = 40


@dataclass
class LocationResult:
    eligible: bool
    confidence: str  # "high" | "low"
    reason: str


def check_location(text: str, rules: dict, remote_flag: Optional[bool] = None) -> LocationResult:
    """`remote_flag` is the collector's own structured remote/on-site flag
    (e.g. Arbeitnow/Lever's `remote` field), when available. It's treated as a
    stronger signal than a text phrase: a source that explicitly marked a
    posting as NOT remote should not be overridden by a stray "fully remote"
    (describing the company in general, not this role) elsewhere in the JD."""
    text_l = (text or "").lower()
    for phrase in rules.get("reject_phrases", []):
        if phrase.strip().lower() in text_l:
            return LocationResult(eligible=False, confidence="high", reason=f"Reject phrase: '{phrase.strip()}'")

    for phrase in rules.get("accept_phrases", []):
        if phrase.strip().lower() in text_l:
            if remote_flag is False:
                return LocationResult(
                    eligible=True, confidence="low",
                    reason=f"Accept phrase '{phrase.strip()}' found, but source marked this posting as not remote",
                )
            return LocationResult(eligible=True, confidence="high", reason=f"Accept phrase: '{phrase.strip()}'")

    if remote_flag is True:
        return LocationResult(eligible=True, confidence="high", reason="Source marked this posting as remote")

    return LocationResult(eligible=True, confidence="low", reason="No explicit remote/location signal found")


@dataclass
class ExperienceResult:
    years_required: Optional[int]
    is_required: bool  # True = "required", False = "preferred" (only meaningful if years_required is not None)
    raw: str


def parse_experience(text: str) -> ExperienceResult:
    text_l = (text or "").lower()
    best: Optional[ExperienceResult] = None
    for m in YEARS_PATTERN.finditer(text_l):
        years = int(m.group(1))
        lo = max(0, m.start() - CONTEXT_WINDOW)
        hi = min(len(text_l), m.end() + CONTEXT_WINDOW)
        window = text_l[lo:hi]
        is_preferred = any(p in window for p in PREFERRED_MARKERS)
        is_required = any(p in window for p in REQUIRED_MARKERS)
        candidate = ExperienceResult(
            years_required=years,
            is_required=is_required or not is_preferred,
            raw=text_l[lo:hi].strip(),
        )
        # keep the highest years figure found (most conservative / most informative)
        if best is None or years > (best.years_required or 0):
            best = candidate

    if best is None:
        return ExperienceResult(years_required=None, is_required=False, raw="not specified")
    return best


def experience_penalty(candidate_years: float, exp: ExperienceResult, penalty_by_gap: dict,
                        preferred_multiplier: float) -> tuple[int, str]:
    """Returns (penalty_points 0-100, human-readable label)."""
    if exp.years_required is None:
        return 0, "not specified"

    gap = exp.years_required - candidate_years
    if gap <= 0:
        label = f"{exp.years_required}+ years {'required' if exp.is_required else 'preferred'} (meets bar)"
        return 0, label

    gap_bucket = str(min(5, max(1, round(gap))))
    penalty = int(penalty_by_gap.get(gap_bucket, 50))
    if not exp.is_required:
        penalty = int(penalty * preferred_multiplier)

    label = f"{exp.years_required}+ years {'required' if exp.is_required else 'preferred'}"
    return penalty, label


def passes_hard_filters(text: str, posted_at, location_rules: dict, max_age_days: int,
                         remote_flag: Optional[bool] = None) -> tuple[bool, LocationResult, str]:
    """Hard-reject stage, run BEFORE technical matching/scoring. Returns
    (passes, location_result, reject_reason)."""
    loc = check_location(text, location_rules, remote_flag)
    if not loc.eligible:
        return False, loc, "location_reject"
    if not within_max_age(posted_at, max_age_days):
        return False, loc, "too_old"
    return True, loc, ""


def within_max_age(posted_at, max_age_days: int) -> bool:
    if posted_at is None:
        return True  # unknown freshness is never hard-filtered out
    now = datetime.now(timezone.utc)
    posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=timezone.utc)
    age_days = (now - posted).total_seconds() / 86400.0
    return age_days <= max_age_days
