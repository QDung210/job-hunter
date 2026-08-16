from src.models import Job, ScoredJob
from src.notifier import MAX_LEN, format_digest_message, format_job_message


def make_scored_job(i: int, score: int = 78) -> ScoredJob:
    job = Job(
        source="greenhouse",
        source_id=str(i),
        title=f"AI Engineer #{i} with a moderately long descriptive title suffix",
        company=f"Company {i} Inc",
        url=f"https://boards.greenhouse.io/company{i}/jobs/{i}",
        description="Python, RAG, LangChain",
    )
    return ScoredJob(job=job, score=score, priority="🟡 GOOD MATCH")


def test_large_digest_never_exceeds_telegram_limit_and_stays_balanced_html():
    """Regression: a 107-job digest previously got truncated mid-HTML-tag and
    Telegram rejected it with a 400 'can't parse entities' error in production."""
    jobs = [make_scored_job(i) for i in range(150)]
    text = format_digest_message(jobs)

    assert len(text) <= MAX_LEN
    # every opened <a>/<b> tag in the message must be closed — a mid-entry cut
    # would leave an unbalanced tag count.
    for tag in ("a", "b"):
        assert text.count(f"<{tag} ") + text.count(f"<{tag}>") == text.count(f"</{tag}>")


def test_small_digest_includes_every_job_with_no_footer():
    jobs = [make_scored_job(i) for i in range(3)]
    text = format_digest_message(jobs)
    for i in range(3):
        assert f"Company {i} Inc" in text
    assert "more" not in text.lower()


def test_single_job_message_stays_under_limit():
    sj = make_scored_job(1, score=95)
    sj.reason = "x" * 10
    text = format_job_message(sj)
    assert len(text) <= MAX_LEN
