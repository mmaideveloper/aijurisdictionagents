from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


@dataclass(frozen=True)
class SlovLexProbeResult:
    year: int
    number: int
    status_code: int
    url: str
    html_sample: str


def _candidate_pairs(*, today: date, max_number_per_year: int) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for year in range(2025, today.year + 1):
        for number in range(1, max_number_per_year + 1):
            pairs.append((year, number))
    return pairs


def _probe_slovlex_law(
    year: int, number: int, *, timeout_seconds: float = 12.0
) -> tuple[SlovLexProbeResult | None, str | None]:
    url = f"https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/{year}/{number}/"
    request = Request(url, headers={"User-Agent": "aijurisdictionagents-slovlex-probe-test/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - controlled HTTPS URL
            status_code = int(getattr(response, "status", 200))
            if status_code != 200:
                return None
            html_sample = response.read(1024).decode("utf-8", errors="ignore")
            return SlovLexProbeResult(
                year=year,
                number=number,
                status_code=status_code,
                url=url,
                html_sample=html_sample,
            ), None
    except HTTPError:
        return None, None
    except URLError as exc:
        return None, str(exc)


@pytest.mark.skipif(
    os.getenv("RUN_SLOVLEX_LIVE_TEST", "0") != "1",
    reason="Set RUN_SLOVLEX_LIVE_TEST=1 to run the live SlovLex probe test.",
)
def test_slovlex_supports_year_and_number_lookup_from_1_2025_to_current_date() -> None:
    today = date.today()
    max_number_per_year = int(os.getenv("SLOVLEX_MAX_NUMBER_PER_YEAR", "80"))

    attempts = 0
    first_success: SlovLexProbeResult | None = None
    transport_error: str | None = None
    for year, number in _candidate_pairs(today=today, max_number_per_year=max_number_per_year):
        attempts += 1
        result, error = _probe_slovlex_law(year, number)
        if error and transport_error is None:
            transport_error = error
        if result is not None:
            first_success = result
            break

    assert attempts > 0
    if first_success is None and transport_error and "Tunnel connection failed" in transport_error:
        pytest.skip(f"Live SlovLex test skipped due to network tunnel limitation: {transport_error}")

    assert first_success is not None, (
        "No SlovLex law URL responded with HTTP 200 while probing "
        f"1/{2025} through year {today.year} with max number {max_number_per_year}."
    )
    assert first_success.year >= 2025
    assert first_success.number >= 1
    assert "<html" in first_success.html_sample.lower() or "<!doctype" in first_success.html_sample.lower()
