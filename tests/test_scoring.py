from datetime import datetime, timedelta, timezone

from src.config import get_config
from src.filters import check_location
from src.models import Job
from src.scoring import score_job
from src.taxonomy import Taxonomy


def make_taxonomy():
    config = get_config()
    return Taxonomy(
        config.keywords["categories"], config.known_terms,
        fuzzy_enabled=True, fuzzy_threshold=90,
    )


def test_strong_agentic_ai_match_scores_high():
    config = get_config()
    taxonomy = make_taxonomy()
    job = Job(
        source="greenhouse", source_id="1", title="AI Agent Engineer", company="Acme AI",
        location_raw="Remote Worldwide", remote=True,
        url="https://boards.greenhouse.io/acme/jobs/1",
        description=(
            "Remote Worldwide. Build autonomous LLM workflows using LangGraph, MCP, "
            "RAG with Qdrant, FastAPI, Python, AWS Bedrock. 2+ years preferred."
        ),
        posted_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    loc = check_location(job.full_text, config.location_rules, job.remote)
    scored = score_job(job, loc, taxonomy, config)

    assert scored.score >= 82
    assert scored.location_eligible is True
    assert "langgraph" in scored.technical_matches
    assert scored.priority in ("🔥 EXCEPTIONAL", "🟢 HIGH MATCH")


def test_backend_title_with_strong_ai_jd_still_scores_reasonably():
    """A generic 'Backend Engineer' title with a heavy agentic/AI stack JD must
    not be dragged down to REVIEW/ignore just because the title lacks 'AI'."""
    config = get_config()
    taxonomy = make_taxonomy()
    job = Job(
        source="lever", source_id="2", title="Backend Engineer", company="Beta Inc",
        location_raw="Remote APAC", remote=True,
        url="https://jobs.lever.co/beta/2",
        description="Python backend role. You'll build with LangChain, RAG, and CrewAI-style multi-agent systems.",
        posted_at=datetime.now(timezone.utc) - timedelta(hours=5),
    )
    loc = check_location(job.full_text, config.location_rules, job.remote)
    scored = score_job(job, loc, taxonomy, config)

    assert scored.score >= 65
    assert any(t.startswith("crewai") for t in scored.transferable_matches)


def test_us_only_job_is_location_ineligible():
    config = get_config()
    job = Job(
        source="greenhouse", source_id="3", title="AI Engineer", company="Gamma LLC",
        location_raw="United States", remote=False,
        url="https://boards.greenhouse.io/gamma/jobs/3",
        description="US citizens only. Python, LangGraph, RAG.",
    )
    loc = check_location(job.full_text, config.location_rules, job.remote)
    assert loc.eligible is False
