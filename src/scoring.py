"""Explainable 0-100 scoring: Technical 35% / Role 15% / Remote 15% /
Freshness 15% / Experience 10% / Company-response 5% / Compensation 5%.
"""
from __future__ import annotations

from datetime import datetime, timezone

from rapidfuzz import fuzz, process

from .filters import (
    ExperienceResult,
    LocationResult,
    experience_penalty,
    parse_experience,
)
from .models import Job, ScoredJob
from .taxonomy import MatchResult, Taxonomy

WEIGHTS = {
    "technical": 0.35,
    "role": 0.15,
    "remote": 0.15,
    "freshness": 0.15,
    "experience": 0.10,
    "response": 0.05,
    "compensation": 0.05,
}

DIRECT_ATS_SOURCES = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}

# Below this, priority_label() returns "IGNORE" per spec. Jobs under this bar
# are excluded from data/seen_jobs.json and the generated feed (main.py) —
# they're irrelevant noise, not worth the persistence/git-diff footprint.
REVIEW_MIN = 65


def technical_score(match: MatchResult) -> int:
    raw = len(match.technical_matches) * 15 + len(match.transferable_matches) * 10
    raw -= len(match.hard_requirements_missing) * 20
    return max(0, min(100, raw))


def role_score(title: str, role_titles: list[str]) -> int:
    if not role_titles:
        return 50
    best = process.extractOne(title, role_titles, scorer=fuzz.token_set_ratio)
    return int(best[1]) if best else 30


def remote_score(loc: LocationResult) -> int:
    if not loc.eligible:
        return 0
    return 100 if loc.confidence == "high" else 55


def freshness_score(posted_at) -> tuple[int, str]:
    if posted_at is None:
        return 50, "unknown"
    now = datetime.now(timezone.utc)
    posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=timezone.utc)
    hours = (now - posted).total_seconds() / 3600.0
    if hours < 0:
        hours = 0
    if hours < 6:
        return 100, "known"
    if hours < 24:
        return 90, "known"
    if hours <= 72:
        return 75, "known"
    if hours <= 168:
        return 55, "known"
    if hours <= 336:
        return 35, "known"
    return 10, "known"


def response_probability(source: str, tech_score: int) -> str:
    if source in DIRECT_ATS_SOURCES and tech_score >= 70:
        return "HIGH"
    if source in DIRECT_ATS_SOURCES:
        return "MEDIUM"
    if tech_score >= 85:
        return "MEDIUM"
    return "UNKNOWN"


def response_score(prob: str) -> int:
    return {"HIGH": 100, "MEDIUM": 60, "LOW": 30, "UNKNOWN": 50}.get(prob, 50)


def compensation_score(job: Job) -> int:
    val = job.salary_max or job.salary_min
    if not val:
        return 50
    if val >= 70000:
        return 100
    if val >= 40000:
        return 75
    if val >= 20000:
        return 50
    return 30


def priority_label(score: int, thresholds: dict) -> str:
    if score >= thresholds.get("hot", 90):
        return "🔥 EXCEPTIONAL"
    if score >= thresholds.get("notify", 82):
        return "🟢 HIGH MATCH"
    if score >= thresholds.get("digest", 75):
        return "🟡 GOOD MATCH"
    if score >= REVIEW_MIN:
        return "⚪ REVIEW"
    return "IGNORE"


def notify_tier(score: int, thresholds: dict) -> str:
    if score >= thresholds.get("notify", 82):
        return "immediate"
    if score >= thresholds.get("digest", 75):
        return "digest"
    return "none"


def recommended_action(score: int, thresholds: dict) -> str:
    if score >= thresholds.get("notify", 82):
        return "APPLY_NOW"
    if score >= thresholds.get("digest", 75):
        return "REVIEW_AND_APPLY"
    return "SKIP"


def build_reason(match: MatchResult, exp_label: str, freshness_conf: str, job: Job) -> str:
    highlights = list(match.technical_matches[:3])
    highlights += [t.split(" ← ")[0] for t in match.transferable_matches[:2]]
    highlight_str = ", ".join(dict.fromkeys(highlights)) if highlights else "general backend/AI stack overlap"
    freshness_note = "recently posted" if freshness_conf == "known" else "posting date unknown"
    return f"{freshness_note.capitalize()} role at {job.company} with strong overlap in {highlight_str}."


def score_job(job: Job, loc: LocationResult, taxonomy: Taxonomy, config) -> ScoredJob:
    match = taxonomy.match(job.full_text)
    tech = technical_score(match)
    role = role_score(job.title, config.role_titles)
    remote = remote_score(loc)
    fresh, fresh_conf = freshness_score(job.posted_at)

    exp: ExperienceResult = parse_experience(job.full_text)
    exp_rules = config.experience_rules
    penalty, exp_label = experience_penalty(
        config.candidate_years, exp,
        exp_rules.get("penalty_by_gap", {}), exp_rules.get("preferred_penalty_multiplier", 0.4),
    )
    exp_score = max(0, 100 - penalty)

    prob = response_probability(job.source, tech)
    resp = response_score(prob)
    comp = compensation_score(job)

    breakdown = {
        "technical": tech, "role": role, "remote": remote,
        "freshness": fresh, "experience": exp_score, "response": resp, "compensation": comp,
    }
    total = sum(breakdown[k] * WEIGHTS[k] for k in WEIGHTS)
    total_int = int(round(total))

    thresholds = config.thresholds
    reason = build_reason(match, exp_label, fresh_conf, job)

    return ScoredJob(
        job=job,
        score=total_int,
        priority=priority_label(total_int, thresholds),
        score_breakdown=breakdown,
        technical_matches=sorted(set(match.technical_matches)),
        transferable_matches=sorted(set(match.transferable_matches)),
        missing_skills=sorted(set(match.missing_skills)),
        hard_requirements_missing=sorted(set(match.hard_requirements_missing)),
        experience_required=exp_label,
        location_eligible=loc.eligible,
        location_confidence=loc.confidence,
        freshness_confidence=fresh_conf,
        response_probability=prob,
        reason=reason,
        recommended_action=recommended_action(total_int, thresholds),
        notify_tier=notify_tier(total_int, thresholds),
        url_status="not_checked",
    )
