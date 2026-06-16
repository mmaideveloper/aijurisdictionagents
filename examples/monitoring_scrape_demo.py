from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlencode
from urllib.request import urlopen


PROMETHEUS_BASE_URL = os.getenv("PROMETHEUS_BASE_URL", "http://127.0.0.1:9091").rstrip("/")


def _query(expression: str) -> list[dict[str, object]]:
    url = f"{PROMETHEUS_BASE_URL}/api/v1/query?{urlencode({'query': expression})}"
    with urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    data = payload.get("data", {})
    result = data.get("result", [])
    if not isinstance(result, list):
        raise RuntimeError(f"Prometheus query returned unexpected result: {payload}")
    return result


def main() -> int:
    active_targets = _active_targets()
    failed_scrapes = [
        target
        for target in active_targets
        if isinstance(target, dict) and target.get("health") != "up"
    ]

    active_probe_instances = {
        labels.get("instance")
        for target in active_targets
        if isinstance(target, dict)
        for labels in [target.get("labels")]
        if isinstance(labels, dict) and labels.get("job") == "jurisdigta-http-probes"
    }
    failed_probes = [
        result
        for result in _failed_results(_query('probe_success{job="jurisdigta-http-probes"}'))
        if isinstance(result.get("metric"), dict)
        and result["metric"].get("instance") in active_probe_instances
    ]

    if failed_scrapes or failed_probes:
        print("Monitoring validation failed.")
        if failed_scrapes:
            print("Failed scrape targets:")
            for target in failed_scrapes:
                print(json.dumps(target.get("labels", {}), sort_keys=True))
        if failed_probes:
            print("Failed HTTP probes:")
            for result in failed_probes:
                print(json.dumps(result.get("metric", {}), sort_keys=True))
        return 1

    print("Monitoring validation passed: all Prometheus scrapes and JurisDigta HTTP probes are healthy.")
    return 0


def _active_targets() -> list[dict[str, object]]:
    url = f"{PROMETHEUS_BASE_URL}/api/v1/targets?state=active"
    with urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus target lookup failed: {payload}")
    data = payload.get("data", {})
    targets = data.get("activeTargets", [])
    if not isinstance(targets, list):
        raise RuntimeError(f"Prometheus target lookup returned unexpected result: {payload}")
    return targets


def _failed_results(results: list[dict[str, object]]) -> list[dict[str, object]]:
    failed: list[dict[str, object]] = []
    for result in results:
        value = result.get("value")
        if isinstance(value, list) and len(value) >= 2 and value[1] != "1":
            failed.append(result)
    return failed


if __name__ == "__main__":
    sys.exit(main())
