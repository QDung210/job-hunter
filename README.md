# Job Hunter

A 100% free, serverless job-alert bot for AI/ML/Backend roles. It discovers jobs
from a dozen free sources, filters and scores them against your profile, and
pings your Telegram when something good shows up — all on GitHub Actions' free
schedule, with no server you need to keep running and no paid API of any kind.

**It never applies for you.** Discover → filter → rank → notify. That's it.

## What it does

1. Collects raw job listings from ~13 free sources (ATS APIs, remote-job
   boards, RSS feeds, JobSpy, a best-effort Wellfound reader).
2. Normalizes them to one schema.
3. Deduplicates across sources (same job posted on Greenhouse *and*
   RemoteOK *and* LinkedIn only gets reported once).
4. Hard-filters out explicit location dealbreakers (e.g. "US citizens only")
   and stale postings older than `max_age_days`.
5. Matches the job description against a broad AI/backend skill taxonomy —
   including **transferable skills** (a JD asking for CrewAI still scores well
   if your profile lists LangGraph experience, because they're the same
   category: agent frameworks).
6. Scores 0-100 with a fully explainable breakdown (Technical 35% / Role 15% /
   Remote 15% / Freshness 15% / Experience 10% / Company-response 5% /
   Compensation 5%).
7. Checks whether the job's URL is still alive (404/410/"position filled" etc.)
   before notifying.
8. Sends a Telegram message — immediately for great matches, batched into a
   digest for good-but-not-great ones.
9. Remembers what it already told you (`data/seen_jobs.json`) so you're never
   notified about the same job twice.

## Architecture

```
GitHub Actions (schedule: hourly "light", every 3h "heavy")
        |
        v
Collectors (independent; one failing never breaks the others)
        |
        v
Normalize -> Deduplicate -> Hard eligibility filter (location, age)
        |
        v
Technical matching + Scoring (taxonomy.py + scoring.py)
        |
        v
URL / staleness check (only for jobs that would be reported)
        |
        v
Save data/seen_jobs.json + data/latest_jobs.json + data/latest_jobs.csv
        |
        v
Telegram notification (immediate for score>=82, digest for 75-81)
```

Two GitHub Actions workflows call the same `python -m src.main` entrypoint:

- **`hunt-jobs.yml`** — hourly. Cheap, no-key API/RSS sources (Greenhouse,
  Lever, Ashby, Workable, SmartRecruiters, RemoteOK, Remotive, Arbeitnow,
  Himalayas, Jobicy, We Work Remotely).
- **`hunt-jobs-heavy.yml`** — every 3 hours. Slower/riskier sources: JobSpy
  (LinkedIn/Indeed/Google/Glassdoor/ZipRecruiter) and the best-effort
  Wellfound reader.

Both share the same `data/seen_jobs.json`, so a job never gets double-notified
just because it was picked up by both schedules.

No Playwright, no headless browser, anywhere — every collector is a plain
HTTP request, which keeps GitHub Actions minutes and dependencies small.

## Supported sources

| Source | Type | Auth | Reliability |
|---|---|---|---|
| Greenhouse | ATS API (per-company) | none | High |
| Lever | ATS API (per-company) | none | High |
| Ashby | ATS API (per-company) | none | High |
| Workable | ATS API (per-company) | none | High |
| SmartRecruiters | ATS API (per-company) | none | Medium (some companies disable the public feed) |
| RemoteOK | Public API | none (needs browser UA) | High |
| Remotive | Public API | none | High |
| Arbeitnow | Public API | none | High |
| Himalayas | Public API | none | Medium (rate-limited, max 20/page) |
| Jobicy | Public API | none | High |
| We Work Remotely | RSS | none | High |
| JobSpy — Indeed | Scraper | none | High |
| JobSpy — ZipRecruiter | Scraper | none | Medium |
| JobSpy — Google Jobs | Scraper | none | Low (needs exact query syntax) |
| JobSpy — LinkedIn | Scraper | none | Low on shared CI IPs |
| JobSpy — Glassdoor | Scraper | none | Low on shared CI IPs |
| Wellfound | Best-effort HTML scrape | none | Low — see Known Limitations |

Every source can be toggled in `config/sources.yaml` without touching code.

## Quick Start

```bash
cd job-hunter
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q                                  # run the test suite
python -m src.main --tier light --dry-run  # collect + score, no Telegram send
```

Check `data/latest_jobs.json` / `data/latest_jobs.csv` after a dry run to see
what it found.

### 1. Create a Telegram bot

1. Open Telegram, message **@BotFather**, send `/newbot`, follow the prompts.
2. Copy the token it gives you (looks like `123456789:AA...`) — this is
   `TELEGRAM_BOT_TOKEN`.

### 2. Find your chat ID

1. Send any message to your new bot (search for it by the username you gave
   it, then press Start / send "hi").
2. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser.
3. Find `"chat":{"id": ...}` in the JSON — that number is `TELEGRAM_CHAT_ID`.
   (Alternative: message `@userinfobot` and it will tell you your ID directly.)

### 3. Push this repo to GitHub

```bash
cd job-hunter
git init
git add .
git commit -m "Initial commit: job hunter bot"
git branch -M main
git remote add origin https://github.com/<you>/<your-repo>.git
git push -u origin main
```

(Use a **public** repo if you want unlimited free GitHub Actions minutes and
want the `n8n` "pull the feed" option to work without extra auth.)

### 4. Add GitHub Secrets

In your repo: **Settings → Secrets and variables → Actions → New repository
secret**. Add:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 5. Enable GitHub Actions

Go to the **Actions** tab of your repo and enable workflows if prompted (first
push to a new repo sometimes requires a manual "I understand my workflows,
enable them" click).

### 6. Test with `workflow_dispatch`

Actions tab → **Hunt Jobs (Light)** → **Run workflow** → tick `dry_run` for
the first try (no Telegram spam) → **Run workflow**. Check the run logs for
the per-source summary and confirm `data/latest_jobs.json` got committed back.
Then run it again without `dry_run` to get your first real alert (if
anything currently clears the threshold).

Repeat for **Hunt Jobs (Heavy)** to test JobSpy/Wellfound.

You can also test Telegram wiring directly, without waiting for a real job match:

```bash
python -m src.main --notify-test
```

## Configuration

Everything lives in `config/*.yaml` — no code changes needed for routine tuning:

- **`config/profile.yaml`** — your location, years of experience, target role
  titles, search queries, known skills (`known_terms`), location accept/reject
  phrases, experience-gap penalties, and score thresholds
  (`notify`/`digest`/`hot`).
- **`config/keywords.yaml`** — the full technical taxonomy: categories,
  aliases, and which categories count as `transferable_group` (see Scoring
  below).
- **`config/sources.yaml`** — enable/disable each collector, its tier
  (`light`/`heavy`), timeouts, retries, and source-specific params.
- **`config/companies.yaml`** — the seed list of company slugs for the
  per-company ATS APIs (Greenhouse/Lever/Ashby/Workable/SmartRecruiters).

### Adding companies to `companies.yaml`

These five sources are per-company, not searchable — you tell the tool which
companies to check. Find a company's slug by visiting:

- Greenhouse: `https://boards.greenhouse.io/<slug>`
- Lever: `https://jobs.lever.co/<slug>`
- Ashby: `https://jobs.ashbyhq.com/<slug>`
- Workable: `https://apply.workable.com/<slug>`
- SmartRecruiters: `https://careers.smartrecruiters.com/<CompanyName>`

If a slug 404s, the collector logs a warning and skips it — it will never
fail the whole run. Prune stale slugs from `companies.yaml` when you notice
the warnings.

## Scoring

Every job gets an explainable 0-100 score:

| Component | Weight | What it measures |
|---|---|---|
| Technical Match | 35% | Taxonomy matches in the JD vs. your `known_terms`, plus transferable-skill credit |
| Role Match | 15% | Fuzzy match of the JD title against your target role titles |
| Remote Eligibility | 15% | Location filter result (high/low confidence) |
| Freshness | 15% | How recently it was posted |
| Experience Match | 10% | Required vs. preferred YOE gap, penalized accordingly |
| Company/Response Potential | 5% | Heuristic (direct ATS source + strong match = higher) — never fabricated |
| Compensation | 5% | Present/absent salary info (never penalizes missing data) |

**Transferable skills**: `config/keywords.yaml` marks some categories as
`transferable_group: true` (agent frameworks, vector DBs, cloud providers,
LLM providers, evaluation/observability tooling, etc). If a JD wants a term in
one of those categories that you don't know, but you know a *different* term
in the **same** category, it counts as a transferable match instead of a gap —
e.g. JD wants Pinecone, you know Qdrant → both are vector databases →
transferable, not missing.

**A generic title is not a rejection.** "Backend Engineer" with a JD full of
Python/RAG/LangChain/agents scores well because Technical Match (35%, driven
by the JD body) outweighs Role Match (15%, driven by the title) — there's no
special-casing needed, it falls out of the weights.

Priority bands: 🔥 EXCEPTIONAL (≥90) · 🟢 HIGH MATCH (≥82) · 🟡 GOOD MATCH
(≥75) · ⚪ REVIEW (≥65) · ignored below 65.

Notification policy (configurable in `profile.yaml` → `thresholds`):
score ≥ 82 → immediate message (with a 🚨🚨 HOT JOB 🚨🚨 prefix at ≥90);
score 75-81 → batched into one digest message per run; below 75 → not sent.

## Adding a new source

1. Create `src/collectors/your_source.py` subclassing `BaseCollector`
   (see `src/collectors/base.py`). Implement `fetch() -> list[Job]`; raise on
   fatal errors — `run()` (called by `main.py`) isolates the exception so one
   bad source never takes down the rest.
2. Add a config block for it in `config/sources.yaml` (`enabled`, `tier`,
   `timeout_seconds`, `retries`, any source-specific params).
3. Wire it up in `build_collectors()` in `src/main.py`.
4. Add a fixture-based unit test if the source has any non-trivial parsing.

## n8n integration (optional)

The core system works with **zero** n8n involvement. If you'd rather route
notifications through an existing n8n instance instead of this repo's own
Telegram sender:

1. In n8n: **Import from File** → `n8n/job-alert-workflow.json`.
2. It has two entry points — use either or both:
   - **Webhook** node: POST a job (or `{"jobs": [...]}`, or an array) to its
     URL from your own automation.
   - **Schedule Trigger → HTTP Request**: edit the HTTP Request node's URL to
     point at your repo's raw `data/latest_jobs.json`
     (`https://raw.githubusercontent.com/<you>/<repo>/main/data/latest_jobs.json`
     — only works out of the box for public repos).
3. Set up a **Telegram** credential in n8n (Settings → Credentials) with your
   bot token, and select it on the "Send Telegram Message" node.
4. Set `TELEGRAM_CHAT_ID` as an n8n environment variable, or replace the
   `chatId` expression on that node with a literal value.
5. Adjust the `IF score >= threshold` node's `value2` (default 75) to taste.
6. Activate the workflow.

This is entirely optional — disabling or never importing it doesn't affect
`hunt-jobs.yml` / `hunt-jobs-heavy.yml` at all.

## Troubleshooting

- **No Telegram messages at all**: run `python -m src.main --notify-test`
  locally (with `.env` filled in) or check the Actions log for "Telegram not
  configured" / "Telegram send failed" warnings. Double check the secrets are
  named exactly `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- **A collector logs "collector FAILED"**: that's expected occasionally (rate
  limits, transient 5xx, a company slug that moved ATS). The run still
  completes using every other source — check the warning text for which one.
- **Data files aren't updating on GitHub**: confirm the workflow has
  `permissions: contents: write` (already set) and that Actions is enabled for
  the repo; check the "Commit updated job data" step's logs.
- **Scheduled runs stopped firing**: GitHub disables `schedule:` triggers
  after 60 days with zero commits to the repo — push anything (or just let the
  bot's own data commits keep it alive) to reset the clock.

## Known limitations

- **Wellfound has no public API** and its `robots.txt` disallows the exact
  `/role/l/...` search paths this collector reads. It's implemented as a
  best-effort HTML scrape (parsing the `__NEXT_DATA__` JSON embedded in the
  page — no JS rendering needed) with a realistic browser User-Agent, very
  low request volume, and silent failure on 403/429/parse errors. If it stops
  working entirely or you'd rather not scrape it at all, set
  `wellfound.enabled: false` in `config/sources.yaml` — nothing else depends
  on it.
- **JobSpy's LinkedIn/Glassdoor/Google support is best-effort** on GitHub
  Actions' shared IPs — expect intermittent empty results or blocks. Indeed is
  the most reliable JobSpy site from CI.
- **SmartRecruiters** postings sometimes come back empty even for a valid
  company ID — some customers disable the public feed on lower plans; that's
  not a bug in this tool.
- **No authoritative free dataset of "which company uses which ATS"
  exists** — `config/companies.yaml` is a small curated seed list you're
  expected to extend yourself as you find companies you care about.
- **`location_confidence: low`** jobs are never auto-rejected by design — an
  ambiguous JD is shown to you rather than silently dropped, so you'll
  sometimes see jobs whose eligibility you need to judge yourself.
