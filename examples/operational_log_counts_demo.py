"""Offline synthetic example: python examples/operational_log_counts_demo.py."""
from pathlib import Path
import argparse
import json
import sys
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.server.log_events import LOKI_FAILURE_PIPELINE, event_counts


def verify_local_loki(url: str) -> None:
    """Seed only a loopback Loki with synthetic records, then query the real pipeline."""
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.scheme != "http":
        raise ValueError("Synthetic seed requires a local HTTP Loki URL")
    run_id = "issue-902-" + uuid4().hex
    logs = [
        'level=info msg="query complete" status=200 query=' + json.dumps(
            'failed level=error status=failed failed_laws=2 ValueError: synthetic '
            'Traceback (most recent call last) status_code=401 authenticated=true'
        ),
        'level=info msg="query complete" query=' + json.dumps(LOKI_FAILURE_PIPELINE),
        json.dumps({"level": "info", "query": "failed to query", "status": "ok"}),
        'level=error msg="synthetic real failure" query="status=ok"',
        'level=info query="status=ok" status=failed',
        'work_retry query="status=ok" error_type=HTTPStatusError',
        'Traceback (most recent call last):',
        'ValueError: synthetic exception',
        'level=info query="incomplete failed',
        json.dumps({"level": "error", "query": "status=ok"}),
    ]
    now = time.time_ns()
    stream = {"stack": "jurisdigta", "container": "jurisdigta-902-synthetic", "run_id": run_id}
    payload = {"streams": [{"stream": stream,
                            "values": [[str(now + i), line] for i, line in enumerate(logs)]}]}
    request = Request(url.rstrip('/') + '/loki/api/v1/push',
                      data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        assert response.status == 204
    selector = '{stack="jurisdigta",run_id="' + run_id + '"}'
    query = 'sum(count_over_time(' + selector + LOKI_FAILURE_PIPELINE + ' [15m]))'
    query_url = url.rstrip('/') + '/loki/api/v1/query?' + urlencode({"query": query})
    with urlopen(query_url, timeout=15) as response:
        result = json.load(response)
    observed = sum(int(float(item['value'][1])) for item in result['data']['result'])
    assert observed == 7, result
    print(json.dumps({"run_id": run_id, "synthetic_lines": len(logs),
                      "expected_failure_lines": 7, "observed_failure_lines": observed,
                      "model_route": "not_applicable_monitoring_only"}))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loki-url", help="Optional loopback Loki for synthetic pipeline validation")
    args = parser.parse_args()
    logs = '\n'.join([
        'level=info msg="flag evaluation succeeded" error=null',
        'level=info msg="Response received from loki" query=' + json.dumps('failed status=error'),
        'level=error msg="synthetic missing file"',
        'work_retry error_type=HTTPStatusError',
        'INFO payload={"status_code":401}',
    ])
    counts = event_counts(logs)
    assert counts['failure'] == counts['retry'] == counts['access_denied'] == 1
    print(counts)
    if args.loki_url:
        verify_local_loki(args.loki_url)
