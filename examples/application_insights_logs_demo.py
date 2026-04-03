from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main() -> None:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    api_key = os.getenv("API_KEY", "aijuris")
    minutes = os.getenv("OBSERVABILITY_MINUTES", "30")
    application = os.getenv("OBSERVABILITY_APPLICATION", "")
    level = os.getenv("OBSERVABILITY_LEVEL", "")
    source = os.getenv("OBSERVABILITY_SOURCE", "")

    query = {
        "minutes": minutes,
    }
    if application:
        query["application"] = application
    if level:
        query["level"] = level
    if source:
        query["source"] = source

    request = Request(
        f"{base_url}/v1/observability/logs?{urlencode(query)}",
        headers={"x-api-key": api_key},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
