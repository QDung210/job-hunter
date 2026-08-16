"""Telegram formatting + sending. HTML parse_mode (simpler escaping than
MarkdownV2), smart truncation to the 4096-char limit, immediate vs digest
messages. The bot token is read only from config/env and is never logged.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

import httpx

from .models import ScoredJob

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 4096

PRIORITY_DISPLAY = {
    "🔥 EXCEPTIONAL": ("🔥", "EXCEPTIONAL MATCH"),
    "🟢 HIGH MATCH": ("🟢", "HIGH MATCH"),
    "🟡 GOOD MATCH": ("🟡", "GOOD MATCH"),
    "⚪ REVIEW": ("⚪", "REVIEW"),
}


def _esc(text) -> str:
    return html.escape(str(text or ""))


def _time_ago(posted_at) -> str:
    if posted_at is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=timezone.utc)
    seconds = max(0.0, (now - posted).total_seconds())
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))} minutes ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hours ago"
    return f"{int(seconds // 86400)} days ago"


def truncate_message(text: str, limit: int = MAX_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 24].rstrip() + "\n\n… (truncated)"


def format_job_message(sj: ScoredJob) -> str:
    j = sj.job
    emoji, label = PRIORITY_DISPLAY.get(sj.priority, ("⚪", "REVIEW"))

    lines: list[str] = []
    if sj.score >= 90:
        lines.append("🚨🚨 <b>HOT JOB</b> 🚨🚨")
    lines.append(f"{emoji} <b>{sj.score}/100 — {label}</b>")
    lines.append("")
    lines.append(f"<b>{_esc(j.title)}</b>")
    lines.append(_esc(j.company))
    lines.append("")

    remote_str = "Worldwide" if j.remote else (j.location_raw or "Unspecified")
    lines.append(f"🌍 Remote: {_esc(remote_str)}")
    if j.salary_raw:
        lines.append(f"💰 {_esc(j.salary_raw)}")
    lines.append(f"🕐 Posted: {_time_ago(j.posted_at)}")
    lines.append(f"📍 Source: {_esc(j.source)}")
    lines.append("")

    if sj.technical_matches:
        lines.append("<b>WHY IT MATCHES</b>")
        for m in sj.technical_matches[:12]:
            lines.append(f"✅ {_esc(m)}")
        lines.append("")

    if sj.transferable_matches:
        lines.append("<b>🔄 TRANSFERABLE</b>")
        for t in sj.transferable_matches[:8]:
            lines.append(f"• {_esc(t)}")
        lines.append("")

    gaps = list(sj.hard_requirements_missing) + [
        m for m in sj.missing_skills if m not in sj.hard_requirements_missing
    ]
    if gaps:
        lines.append("<b>⚠️ GAPS</b>")
        for g in sj.hard_requirements_missing[:5]:
            lines.append(f"• {_esc(g)} (required)")
        soft_gaps = [m for m in sj.missing_skills if m not in sj.hard_requirements_missing][:5]
        for g in soft_gaps:
            lines.append(f"• {_esc(g)}")
        lines.append("")

    lines.append(f"🎯 Response potential: {sj.response_probability}")
    lines.append("")
    lines.append(f"Reason: {_esc(sj.reason)}")
    lines.append("")
    lines.append(f'👉 <a href="{_esc(j.dedupe_url)}">APPLY</a>')

    return truncate_message("\n".join(lines))


def format_digest_message(jobs: list[ScoredJob]) -> str:
    lines = [f"<b>📋 DIGEST — {len(jobs)} good match(es), score 75-81</b>", ""]
    for sj in jobs:
        j = sj.job
        lines.append(f"🟡 {sj.score}/100 — <b>{_esc(j.title)}</b> @ {_esc(j.company)}")
        lines.append(f'   <a href="{_esc(j.dedupe_url)}">Apply</a> · {_esc(j.source)} · {_time_ago(j.posted_at)}')
        lines.append("")
    return truncate_message("\n".join(lines))


class TelegramNotifier:
    def __init__(self, bot_token: str | None, chat_id: str | None, timeout: float = 10.0):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.configured:
            logger.warning("Telegram not configured (missing TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID) — skipping send")
            return False

        url = TELEGRAM_API.format(token=self.bot_token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        for attempt in range(2):
            try:
                resp = httpx.post(url, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    return True
                logger.warning("Telegram send failed (status %s), attempt %s", resp.status_code, attempt + 1)
            except httpx.HTTPError as e:
                logger.warning("Telegram send error (attempt %s): %s", attempt + 1, e)
        return False
