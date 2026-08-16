from src.dedupe import Deduper
from src.models import Job


def make_job(**kwargs):
    defaults = dict(
        source="greenhouse", source_id="1", title="AI Engineer", company="Acme Inc",
        url="https://boards.greenhouse.io/acme/jobs/123",
        description="Python, LangGraph, RAG",
    )
    defaults.update(kwargs)
    return Job(**defaults)


def test_exact_url_dedupe_ignores_tracking_params():
    deduper = Deduper({})
    job1 = make_job()
    assert not deduper.is_duplicate(job1)
    deduper.register(job1, score=80, notified=False)

    job2 = make_job(url="https://boards.greenhouse.io/acme/jobs/123?utm_source=newsletter")
    assert deduper.is_duplicate(job2)


def test_fuzzy_cross_source_dedupe_same_company_and_title():
    deduper = Deduper({})
    job1 = make_job(source="greenhouse", url="https://boards.greenhouse.io/acme/jobs/123")
    deduper.register(job1, score=80, notified=False)

    job2 = make_job(source="remoteok", url="https://remoteok.com/remote-jobs/999", location_raw=None)
    assert deduper.is_duplicate(job2)


def test_different_company_is_not_a_duplicate():
    deduper = Deduper({})
    job1 = make_job(company="Acme Inc")
    deduper.register(job1, score=80, notified=False)

    job2 = make_job(company="Totally Different Co", url="https://x.com/y")
    assert not deduper.is_duplicate(job2)


def test_within_run_duplicates_are_caught_after_register():
    """Two sources returning the same job in the SAME run must be caught too —
    dedupe registers provisionally as soon as a job is confirmed non-duplicate."""
    deduper = Deduper({})
    job1 = make_job(source="greenhouse", url="https://boards.greenhouse.io/acme/jobs/123")
    assert not deduper.is_duplicate(job1)
    deduper.register(job1, score=0, notified=False)

    job2 = make_job(source="remoteok", url="https://remoteok.com/remote-jobs/999")
    assert deduper.is_duplicate(job2)
