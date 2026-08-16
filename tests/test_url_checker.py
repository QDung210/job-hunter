import httpx
import respx

from src.url_checker import check_url


@respx.mock
def test_404_is_stale():
    respx.head("https://example.com/job/1").mock(return_value=httpx.Response(404))
    assert check_url("https://example.com/job/1") == "stale"


@respx.mock
def test_closed_phrase_in_body_is_stale():
    respx.head("https://example.com/job/2").mock(return_value=httpx.Response(200))
    respx.get("https://example.com/job/2").mock(
        return_value=httpx.Response(200, text="Sorry, this position has been filled.")
    )
    assert check_url("https://example.com/job/2") == "stale"


@respx.mock
def test_live_job_is_ok():
    respx.head("https://example.com/job/3").mock(return_value=httpx.Response(200))
    respx.get("https://example.com/job/3").mock(
        return_value=httpx.Response(200, text="Great AI Engineer role, apply now!")
    )
    assert check_url("https://example.com/job/3") == "ok"


@respx.mock
def test_network_error_is_unknown_not_stale():
    respx.head("https://example.com/job/4").mock(side_effect=httpx.ConnectTimeout("timeout"))
    respx.get("https://example.com/job/4").mock(side_effect=httpx.ConnectTimeout("timeout"))
    assert check_url("https://example.com/job/4") == "unknown"


@respx.mock
def test_403_anti_bot_is_unknown_not_stale():
    respx.head("https://example.com/job/5").mock(return_value=httpx.Response(403))
    respx.get("https://example.com/job/5").mock(return_value=httpx.Response(403))
    assert check_url("https://example.com/job/5") == "unknown"
