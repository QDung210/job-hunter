"""Broad, transferable-skill-aware keyword taxonomy matching.

A JD term is:
  - a technical_match  if the candidate's known_terms contains that exact term
  - a transferable_match if the term's category is transferable_group AND the
    candidate knows a DIFFERENT term in that same category
    (e.g. JD wants "CrewAI", candidate knows "LangGraph" -> both agent_frameworks)
  - a missing_skill otherwise (and further flagged hard_requirements_missing if
    it appears near "required"/"must have"/"minimum" language in the JD text)
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

REQUIRED_MARKERS = [
    "required", "require", "must have", "must-have", "mandatory",
    "minimum of", "need to have", "essential",
]
PREFERRED_MARKERS = [
    "preferred", "nice to have", "nice-to-have", "a plus", "is a plus",
    "bonus", "ideally", "plus if",
]
CONTEXT_WINDOW = 60


@dataclass
class MatchResult:
    technical_matches: list[str] = field(default_factory=list)
    transferable_matches: list[str] = field(default_factory=list)  # "jd_term ← experience with known_term"
    missing_skills: list[str] = field(default_factory=list)
    hard_requirements_missing: list[str] = field(default_factory=list)
    categories_hit: set[str] = field(default_factory=set)


class Taxonomy:
    def __init__(self, categories: dict, known_terms: set[str], fuzzy_enabled: bool = True,
                 fuzzy_threshold: int = 90):
        self.categories = categories or {}
        self.known_terms = {t.lower() for t in known_terms}
        self.fuzzy_enabled = fuzzy_enabled
        self.fuzzy_threshold = fuzzy_threshold

        self.term_category: dict[str, set[str]] = defaultdict(set)
        self._patterns: dict[str, re.Pattern] = {}
        for cat_name, cat_cfg in self.categories.items():
            for term in cat_cfg.get("terms", []):
                term_l = term.lower()
                self.term_category[term_l].add(cat_name)
                if term_l not in self._patterns:
                    self._patterns[term_l] = re.compile(
                        r"(?<!\w)" + re.escape(term_l) + r"(?!\w)", re.IGNORECASE
                    )

        self.known_by_category: dict[str, set[str]] = defaultdict(set)
        for term in self.known_terms:
            for cat in self.term_category.get(term, ()):
                self.known_by_category[cat].add(term)

    def _is_transferable_group(self, cat: str) -> bool:
        return bool(self.categories.get(cat, {}).get("transferable_group"))

    def match(self, text: str) -> MatchResult:
        text_l = (text or "").lower()
        result = MatchResult()

        matched_terms: dict[str, dict[str, Any]] = {}
        for term, pattern in self._patterns.items():
            m = pattern.search(text_l)
            if m:
                matched_terms[term] = {"pos": m.start(), "end": m.end(), "fuzzy": False}
            elif self.fuzzy_enabled and len(term) >= 4:
                if fuzz.partial_ratio(term, text_l) >= self.fuzzy_threshold:
                    matched_terms[term] = {"pos": None, "end": None, "fuzzy": True}

        for term, info in matched_terms.items():
            cats = self.term_category.get(term, set())
            result.categories_hit |= cats

            if term in self.known_terms:
                result.technical_matches.append(term)
                continue

            transferred = False
            for cat in cats:
                if not self._is_transferable_group(cat):
                    continue
                known_in_cat = [k for k in self.known_by_category.get(cat, ()) if k != term]
                if known_in_cat:
                    result.transferable_matches.append(f"{term} ← experience with {known_in_cat[0]}")
                    transferred = True
                    break

            if not transferred:
                result.missing_skills.append(term)
                if info["pos"] is not None and self._near_required_marker(text_l, info["pos"], info["end"]):
                    result.hard_requirements_missing.append(term)

        return result

    @staticmethod
    def _near_required_marker(text_l: str, start: int, end: int) -> bool:
        lo = max(0, start - CONTEXT_WINDOW)
        hi = min(len(text_l), end + CONTEXT_WINDOW)
        window = text_l[lo:hi]
        has_required = any(m in window for m in REQUIRED_MARKERS)
        has_preferred = any(m in window for m in PREFERRED_MARKERS)
        return has_required and not has_preferred
