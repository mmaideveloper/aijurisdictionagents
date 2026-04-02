import httpx
from openai import RateLimitError

from aijurisdictionagents.llm import embeddings


def _rate_limit_response(*, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://example.test/embeddings")
    return httpx.Response(429, headers=headers, request=request)


def test_request_embeddings_with_retry_retries_rate_limits(monkeypatch) -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def flaky_request() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RateLimitError(
                "retry after 1 seconds",
                response=_rate_limit_response(headers={"retry-after": "1"}),
                body={},
            )
        return "ok"

    monkeypatch.setattr(embeddings.time, "sleep", fake_sleep)

    result = embeddings._request_embeddings_with_retry(flaky_request, max_attempts=4)

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [1.0, 1.0]


def test_retry_delay_seconds_parses_rate_limit_message_without_headers() -> None:
    error = RateLimitError(
        "Please retry after 42 seconds.",
        response=_rate_limit_response(),
        body={},
    )

    delay = embeddings._retry_delay_seconds(error, attempt=2)

    assert delay == 42.0
