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
    missing_queries = [
        expression
        for expression in (
            "jurisdigta_ollama_up",
            "jurisdigta_ai_model_total_tokens_window",
            "jurisdigta_ai_model_top_case_total_tokens_window",
            'jurisdigta_laws_total{name="laws_imported"}',
            "jurisdigta_laws_last_processed_number",
            "jurisdigta_laws_last_processed_year",
            "jurisdigta_component_status{component=\"court_decision_collector\"}",
            "jurisdigta_court_decisions_total",
            "jurisdigta_court_decision_latest_stored_issue_date_timestamp_seconds",
        )
        if not _query(expression)
    ]
    missing_alerts = _missing_alert_rules(
        {
            "JurisDigtaOllamaExporterDown",
            "JurisDigtaOllamaConfiguredModelMissing",
            "JurisDigtaPaidModelTokenSpike",
            "JurisDigtaPaidModelCostSpike",
        }
    )

    if failed_scrapes or failed_probes or missing_queries or missing_alerts:
        print("Monitoring validation failed.")
        if failed_scrapes:
            print("Failed scrape targets:")
            for target in failed_scrapes:
                print(json.dumps(target.get("labels", {}), sort_keys=True))
        if failed_probes:
            print("Failed HTTP probes:")
            for result in failed_probes:
                print(json.dumps(result.get("metric", {}), sort_keys=True))
        if missing_queries:
            print("Missing expected Prometheus metrics:")
            for expression in missing_queries:
                print(expression)
        if missing_alerts:
            print("Missing expected Prometheus alert rules:")
            for alert_name in sorted(missing_alerts):
                print(alert_name)
        return 1

    print(
        "Monitoring validation passed: Prometheus scrapes, JurisDigta HTTP probes, "
        "AI token metrics, laws collector metrics, court-decision metrics, "
        "and AI model alert rules are healthy."
    )
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


def _missing_alert_rules(expected: set[str]) -> set[str]:
    url = f"{PROMETHEUS_BASE_URL}/api/v1/rules"
    with urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus rules lookup failed: {payload}")
    groups = payload.get("data", {}).get("groups", [])
    found: set[str] = set()
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict):
                continue
            rules = group.get("rules", [])
            if not isinstance(rules, list):
                continue
            for rule in rules:
                if isinstance(rule, dict) and isinstance(rule.get("name"), str):
                    found.add(rule["name"])
    return expected - found


if __name__ == "__main__":
    sys.exit(main())
