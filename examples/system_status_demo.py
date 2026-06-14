from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main() -> int:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    api_key = os.getenv("API_KEY", "aijuris")
    request = Request(
        f"{base_url}/v1/system/status?minutes=60",
        headers={"x-api-key": api_key},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"Status request failed: HTTP {exc.code} {exc.read().decode('utf-8')}")
        return 1

    api = payload.get("api", {})
    laws = payload.get("laws_collector", {})
    errors = payload.get("errors", {}).get("by_application", {})
    print(f"Overall status: {payload.get('status')}")
    print(f"API: {api.get('status')} version={api.get('api_version')}")
    print(
        "Laws collector: "
        f"{laws.get('status')} last_law={laws.get('last_processed_law')} "
        f"next={laws.get('next_law_to_check')} last_run={laws.get('last_collector_run_at')}"
    )
    print(f"Errors in last hour: {errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
