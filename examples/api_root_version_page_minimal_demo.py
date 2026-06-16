from __future__ import annotations

import urllib.request


API_ROOT_URL = "http://127.0.0.1:8080/"


def main() -> None:
    request = urllib.request.Request(API_ROOT_URL, headers={"Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=10) as response:
        content_type = response.headers.get("content-type", "")
        body = response.read().decode("utf-8")

    print("status page content-type:", content_type)
    print("contains api_version:", '"api_version"' in body or "&quot;api_version&quot;" in body)


if __name__ == "__main__":
    main()
