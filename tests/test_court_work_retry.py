from datetime import datetime, timedelta, timezone

import httpx
import pytest

from services.court_decision_collector.retry import schedule_retry

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


@pytest.mark.parametrize("status", [404, 410, 408, 429, 500, 503])
def test_recoverable_statuses_have_durable_cooldown(status):
    response = httpx.Response(status, request=httpx.Request("GET", "https://source.invalid"))
    error = httpx.HTTPStatusError("synthetic", request=response.request, response=response)
    result = schedule_retry(error, attempt=1, reference="synthetic", now=NOW)
    assert result is not None
    assert result.next_attempt_at >= NOW + timedelta(seconds=60)


@pytest.mark.parametrize("header", ["7200", "Fri, 09 Oct 2026 02:00:00 GMT"])
def test_retry_after_is_a_lower_bound(header):
    response = httpx.Response(429, headers={"Retry-After": header},
                              request=httpx.Request("GET", "https://source.invalid"))
    error = httpx.HTTPStatusError("synthetic", request=response.request, response=response)
    result = schedule_retry(error, attempt=1, reference="synthetic", now=NOW)
    assert result.next_attempt_at == NOW + timedelta(hours=2)


def test_exhausted_missing_record_is_retained_for_weekly_recheck():
    response = httpx.Response(404, request=httpx.Request("GET", "https://source.invalid"))
    error = httpx.HTTPStatusError("synthetic", request=response.request, response=response)
    result = schedule_retry(error, attempt=5, reference="synthetic", now=NOW)
    assert result.next_attempt_at == NOW + timedelta(days=7)


def test_network_failure_retries_but_storage_and_programming_errors_abort():
    assert schedule_retry(httpx.ConnectError("synthetic"), attempt=2, reference="x", now=NOW)
    assert schedule_retry(ValueError("schema defect"), attempt=2, reference="x", now=NOW) is None
