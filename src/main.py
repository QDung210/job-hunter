"""CLI entrypoint: collect -> dedupe -> hard filter -> match+score -> URL check
-> save seen/feed -> Telegram notify. Run with `python -m src.main --tier light`.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .collectors.arbeitnow import ArbeitnowCollector
from .collectors.ashby import AshbyCollector
from .collectors.greenhouse import GreenhouseCollector
from .collectors.himalayas import HimalayasCollector
from .collectors.jobicy import JobicyCollector
from .collectors.jobspy_collector import JobSpyCollector
from .collectors.lever import LeverCollector
from .collectors.remoteok import RemoteOkCollector
from .collectors.remotive import RemotiveCollector
from .collectors.smartrecruiters import SmartRecruitersCollector
from .collectors.wellfound import WellfoundCollector
from .collectors.weworkremotely import WeWorkRemotelyCollector
from .collectors.workable import WorkableCollector
from .config import DATA_DIR, get_config
from .dedupe import Deduper
from .filters import passes_hard_filters
from .models import Job, ScoredJob
from .notifier import TelegramNotifier, format_digest_message, format_job_message
from .scoring import REVIEW_MIN, score_job
from .storage import load_seen_jobs, prune_seen_jobs, save_latest_jobs, save_seen_jobs
from .taxonomy import Taxonomy
from .url_checker import check_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # keep per-request noise out of the run summary
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("job_hunter")

SEEN_JOBS_PATH = DATA_DIR / "seen_jobs.json"
LATEST_JSON_PATH = DATA_DIR / "latest_jobs.json"
LATEST_CSV_PATH = DATA_DIR / "latest_jobs.csv"


def build_collectors(config, tier: str):
    collectors = []
    enabled = set(config.enabled_sources(tier=tier))
    companies = config.companies or {}

    if "greenhouse" in enabled:
        collectors.append(GreenhouseCollector(config.source_cfg("greenhouse"), companies.get("greenhouse", [])))
    if "lever" in enabled:
        collectors.append(LeverCollector(config.source_cfg("lever"), companies.get("lever", [])))
    if "ashby" in enabled:
        collectors.append(AshbyCollector(config.source_cfg("ashby"), companies.get("ashby", [])))
    if "workable" in enabled:
        collectors.append(WorkableCollector(config.source_cfg("workable"), companies.get("workable", [])))
    if "smartrecruiters" in enabled:
        collectors.append(SmartRecruitersCollector(config.source_cfg("smartrecruiters"), companies.get("smartrecruiters", [])))
    if "remoteok" in enabled:
        collectors.append(RemoteOkCollector(config.source_cfg("remoteok")))
    if "remotive" in enabled:
        collectors.append(RemotiveCollector(config.source_cfg("remotive"), config.search_queries))
    if "arbeitnow" in enabled:
        collectors.append(ArbeitnowCollector(config.source_cfg("arbeitnow")))
    if "himalayas" in enabled:
        collectors.append(HimalayasCollector(config.source_cfg("himalayas")))
    if "jobicy" in enabled:
        collectors.append(JobicyCollector(config.source_cfg("jobicy")))
    if "weworkremotely" in enabled:
        collectors.append(WeWorkRemotelyCollector(config.source_cfg("weworkremotely")))
    if "jobspy" in enabled:
        collectors.append(JobSpyCollector(config.source_cfg("jobspy"), config.search_queries))
    if "wellfound" in enabled:
        collectors.append(WellfoundCollector(config.source_cfg("wellfound")))

    return collectors


def run(tier: str = "all", dry_run: bool = False) -> int:
    config = get_config()
    taxonomy = Taxonomy(
        config.keywords.get("categories", {}),
        config.known_terms,
        fuzzy_enabled=config.keywords.get("fuzzy", {}).get("enabled", True),
        fuzzy_threshold=int(config.keywords.get("fuzzy", {}).get("threshold", 90)),
    )

    collectors = build_collectors(config, tier)
    raw_jobs: list[Job] = []
    for collector in collectors:
        raw_jobs.extend(collector.run())

    logger.info("Total raw: %d", len(raw_jobs))

    # In-run dedup: collapses the SAME job appearing via multiple sources
    # WITHIN this single collection run (e.g. a direct Greenhouse posting also
    # picked up by an aggregator). Starts empty every run — this is NOT the
    # cross-run "don't re-notify" mechanism (that's `history` below). If this
    # used the persisted cross-run history instead, every job ever seen would
    # be excluded from scoring on every subsequent run, and data/latest_jobs.json
    # would shrink towards zero instead of reflecting currently-live matches.
    run_dedup = Deduper({})
    deduped_jobs: list[Job] = []
    for job in raw_jobs:
        if run_dedup.is_duplicate(job):
            continue
        run_dedup.register(job, score=0, notified=False)
        deduped_jobs.append(job)

    logger.info("Deduped: %d", len(deduped_jobs))

    # Cross-run history: used ONLY to avoid re-notifying a job already alerted
    # on in a previous run, and to persist score/last-seen for expiry pruning.
    history = load_seen_jobs(SEEN_JOBS_PATH)
    history = prune_seen_jobs(history, config.seen_jobs_expiry_days)
    history_dedup = Deduper(history)

    location_rules = config.location_rules
    max_age_days = config.max_age_days

    eligible: list[tuple[Job, object]] = []
    for job in deduped_jobs:
        passes, loc, _reason = passes_hard_filters(
            job.full_text, job.posted_at, location_rules, max_age_days, remote_flag=job.remote
        )
        if passes:
            eligible.append((job, loc))

    logger.info("Eligible: %d", len(eligible))

    scored_jobs: list[ScoredJob] = [score_job(job, loc, taxonomy, config) for job, loc in eligible]

    thresholds = config.thresholds
    digest_th = thresholds.get("digest", 75)
    notify_th = thresholds.get("notify", 82)
    digest_or_better = sum(1 for sj in scored_jobs if sj.score >= digest_th)
    notify_or_better = sum(1 for sj in scored_jobs if sj.score >= notify_th)
    logger.info("Score >=%s: %d", digest_th, digest_or_better)
    logger.info("Score >=%s: %d", notify_th, notify_or_better)

    url_check_cfg = config.url_check_config
    if url_check_cfg.get("enabled", True):
        min_score = url_check_cfg.get("min_score_to_check", digest_th)
        timeout = float(url_check_cfg.get("timeout_seconds", 6))
        for sj in scored_jobs:
            if sj.score >= min_score:
                sj.url_status = check_url(sj.job.dedupe_url, timeout)

    notifications_sent = 0
    if not dry_run:
        reportable = [
            sj for sj in scored_jobs
            if sj.score >= digest_th and sj.url_status != "stale" and not history_dedup.was_notified(sj.job)
        ]
        immediate = [sj for sj in reportable if sj.notify_tier == "immediate"]
        digest = [sj for sj in reportable if sj.notify_tier == "digest"]

        for sj in immediate:
            ok = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id).send(format_job_message(sj))
            if ok:
                notifications_sent += 1
            history_dedup.register(sj.job, sj.score, notified=ok)

        if digest:
            ok = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id).send(format_digest_message(digest))
            if ok:
                notifications_sent += 1
            for sj in digest:
                history_dedup.register(sj.job, sj.score, notified=ok)

    logger.info("Notifications: %d", notifications_sent)

    # Below REVIEW_MIN a job is "IGNORE" per spec — not worth persisting to
    # seen_jobs.json or the generated feed (keeps both from ballooning with
    # thousands of irrelevant postings re-saved on every hourly run).
    worth_keeping = [sj for sj in scored_jobs if sj.score >= REVIEW_MIN]

    # Persist every kept job's latest score/last-seen timestamp (register()
    # ORs the notified flag, so True values set above are preserved here).
    for sj in worth_keeping:
        history_dedup.register(sj.job, sj.score, notified=False)

    save_seen_jobs(SEEN_JOBS_PATH, history_dedup.seen)
    worth_keeping_sorted = sorted(worth_keeping, key=lambda sj: sj.score, reverse=True)
    save_latest_jobs(LATEST_JSON_PATH, LATEST_CSV_PATH, worth_keeping_sorted)

    return 0


def send_test_notification() -> int:
    config = get_config()
    notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)
    if notifier.send("✅ Job Hunter test notification — Telegram wiring works."):
        logger.info("Test notification sent successfully.")
        return 0
    logger.error("Test notification failed — check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Job Hunter — free, serverless AI/backend job alert bot")
    parser.add_argument("--tier", choices=["light", "heavy", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="Skip Telegram sends; still writes data files")
    parser.add_argument("--notify-test", action="store_true", help="Send one test Telegram message and exit")
    args = parser.parse_args(argv)

    if args.notify_test:
        return send_test_notification()

    return run(tier=args.tier, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
