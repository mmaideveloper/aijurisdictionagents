from __future__ import annotations

from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def probe_slovlex(*, from_year: int = 2025, max_number_per_year: int = 80) -> tuple[int, int, str] | None:
    today = date.today()
    for year in range(from_year, today.year + 1):
        for number in range(1, max_number_per_year + 1):
            url = f"https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/{year}/{number}/"
            request = Request(url, headers={"User-Agent": "aijurisdictionagents-slovlex-demo/1.0"})
            try:
                with urlopen(request, timeout=12.0) as response:  # noqa: S310 - controlled HTTPS URL
                    if int(getattr(response, "status", 200)) == 200:
                        return year, number, url
            except (HTTPError, URLError):
                continue
    return None


def main() -> None:
    result = probe_slovlex(from_year=2025, max_number_per_year=80)
    if result is None:
        print("No matching SlovLex law found in the probed range (from 1/2025 up to current date).")
        return

    year, number, url = result
    print("First reachable SlovLex law by number/year:")
    print(f"  year={year}")
    print(f"  number={number}")
    print(f"  url={url}")


if __name__ == "__main__":
    main()
