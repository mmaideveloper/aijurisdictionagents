from __future__ import annotations

import json


def main() -> int:
    sample_payload = {
        "metadata": {
            "law_citations": [
                {
                    "law_identifier": "1/1993 Z. z.",
                    "title": "Prvy zakon",
                    "version_token": "19930101",
                    "effective_from": "1993-01-01",
                    "open_url": (
                        "/v1/laws/source?country_code=SK&collection_code=ZZ"
                        "&law_year=1993&law_number=1&version_token=19930101&artifact_kind=html"
                    ),
                    "summary": (
                        "1/1993 Z. z. (Prvy zakon), version 19930101, "
                        "effective from 1993-01-01"
                    ),
                }
            ]
        }
    }
    print(json.dumps(sample_payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
