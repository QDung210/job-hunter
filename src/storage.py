"""Persistence for data/seen_jobs.json (with expiry pruning) and the generated
data/latest_jobs.json / .csv feed."""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CSV_FIELDNAMES = [
    "score", "priority", "title", "company", "source", "url", "posted_at",
    "remote", "location", "salary", "experience_required", "location_eligible",
    "location_confidence", "response_probability", "recommended_action",
]


def load_seen_jobs(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s (%s) — starting with empty seen-jobs state", path, e)
        return {}


def prune_seen_jobs(seen: dict, expiry_days: int) -> dict:
    now = datetime.now(timezone.utc)
    pruned = {}
    for key, rec in seen.items():
        last_seen_str = rec.get("last_seen")
        try:
            last_seen = datetime.fromisoformat(last_seen_str)
        except (TypeError, ValueError):
            pruned[key] = rec  # keep malformed records rather than silently losing state
            continue
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        age_days = (now - last_seen).total_seconds() / 86400.0
        if age_days <= expiry_days:
            pruned[key] = rec
    return pruned


def save_seen_jobs(path: Path, seen: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False, sort_keys=True)


def save_latest_jobs(json_path: Path, csv_path: Path, scored_jobs: list) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    records = [sj.to_output_dict() for sj in scored_jobs]

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r)
