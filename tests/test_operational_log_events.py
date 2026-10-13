import json
from pathlib import Path
import re

import pytest

from scripts.server.log_events import (
    FAILURE_PATTERN, LOKI_FAILURE_PIPELINE, classify_line, event_counts,
)
from scripts.server.write_system_status import _count_error_lines, _recent_error_lines


@pytest.mark.parametrize("line", [
    'level=info msg="flag evaluation succeeded" error=<nil>',
    '{"level":"info","message":"flag evaluation succeeded","error":null}',
    'finished failed_laws=0',
    '2026-10-09 | INFO | worker | response error=null',
])
def test_success_with_error_fields_is_not_a_failure(line):
    assert classify_line(line) == "success"
    assert not re.search(FAILURE_PATTERN, line)
    assert _count_error_lines(line) == 0


@pytest.mark.parametrize("line", [
    'level=error msg="failed stat"',
    '{"level":"fatal","message":"storage unavailable"}',
    '2026-10-09 | ERROR | worker | unavailable',
    'collector_worker_error status=error error_type=HTTPStatusError',
    'summary failed_laws=2',
    'ERROR database unavailable',
    'Failed to connect to upstream',
])
def test_real_failures_remain_counted(line):
    assert classify_line(line) == "failure"
    assert re.search(FAILURE_PATTERN, line)
    assert _count_error_lines(line) == 1


def test_retry_and_security_denials_are_separate_and_not_silenced():
    text = '\n'.join([
        'work_retry error_type=HTTPStatusError',
        'INFO mcp_wire_response payload={"status_code": 401}',
        'INFO status_code=403 authenticated=true',
    ])
    counts = event_counts(text)
    assert counts["retry"] == 1
    assert counts["access_denied"] == 1
    assert counts["failure"] == 1


def test_traceback_and_exact_duplicate_are_not_multiple_failure_events():
    text = '\n'.join([
        'Traceback (most recent call last):',
        '  File "synthetic.py", line 1',
        '    raise ValueError("synthetic")',
        'ValueError: synthetic',
        'level=error msg="independent failure"',
        'level=error msg="independent failure"',
    ])
    assert event_counts(text)["failure"] == 2


def test_logged_error_with_its_traceback_counts_once():
    text = 'level=error msg="synthetic crash"\nTraceback (most recent call last):\n  synthetic frame\nValueError: synthetic'
    assert event_counts(text)["failure"] == 1


def test_recent_errors_omit_success_but_preserve_retry_diagnostics():
    text = 'level=info msg="flag evaluation succeeded" error=null\nwork_retry error_type=HTTPStatusError'
    errors = _recent_error_lines(text)
    assert len(errors) == 1
    assert 'work_retry' in errors[0]['message']


def test_dashboard_filters_share_failure_contract():
    path = Path(__file__).resolve().parents[1] / 'Deployment/monitoring/grafana/dashboards/jurisdigta-system-logs.json'
    dashboard = json.loads(path.read_text(encoding='utf-8'))
    queries = [t['expr'] for p in dashboard['panels'] for t in p.get('targets', [])]
    escaped = json.dumps(FAILURE_PATTERN, ensure_ascii=False)
    assert sum(escaped in q for q in queries) == 4
    assert sum(LOKI_FAILURE_PIPELINE in q for q in queries) == 4
    assert any('matching lines' in p.get('description', '').lower() for p in dashboard['panels'])


@pytest.mark.parametrize("query", [
    'failed to query', 'level=error', 'status=failed', 'failed_laws=2',
    'ValueError: synthetic', 'Traceback (most recent call last)',
    'status_code=401 authenticated=true', FAILURE_PATTERN,
])
@pytest.mark.parametrize("format", ["logfmt", "json"])
def test_query_metadata_does_not_create_failures_or_denials(query, format):
    record = {"level": "info", "msg": "Response received from loki", "query": query,
              "status": "ok", "statusCode": 200}
    line = json.dumps(record) if format == "json" else ' '.join(
        f'{key}={json.dumps(value)}' if key in {"msg", "query"} else f'{key}={value}'
        for key, value in record.items()
    )
    assert classify_line(line) == "success"
    assert _count_error_lines(line) == 0
    assert _recent_error_lines(line) == []


@pytest.mark.parametrize("event", [
    'level=error msg="query unavailable"',
    'level=info msg="failed to query"',
    'level=info status=failed', 'level=info failed_laws=2',
    'level=info error_type=HTTPStatusError',
    'level=info status_code=403 authenticated=true',
    'level=info msg="ValueError: synthetic"',
])
def test_genuine_failure_survives_query_removal(event):
    line = event + ' query=' + json.dumps('level=info status=ok')
    assert classify_line(line) == "failure"
    assert _count_error_lines(line) == 1


def test_query_removal_preserves_escaped_quotes_trailing_fields_and_unknown():
    query = json.dumps('{stack="synthetic"} |~ "failed"')
    assert classify_line(f'level=info query={query} status=failed') == "failure"
    assert classify_line(f'query={query}') == "unknown"
    assert classify_line('level=info query="incomplete failed') == "failure"
    assert classify_line(f'work_retry query={query} error_type=HTTPStatusError') == "retry"
    assert classify_line(f'level=info query={query} status_code=401') == "access_denied"
    # Text in an escaped message is an actual diagnostic, not a query field.
    line = 'level=info msg=' + json.dumps('query="failed to connect"')
    assert classify_line(line) == "failure"


def test_json_actual_failure_and_security_outcome_survive_query_removal():
    for record in [
        {"level": "error", "query": "status=ok"},
        {"level": "info", "message": "failed to connect", "query": "status=ok"},
        {"level": "info", "status": "failed", "query": "status=ok"},
    ]:
        assert classify_line(json.dumps(record)) == "failure"


def test_all_failure_panels_use_query_normalization_and_raw_logs_do_not():
    root = Path(__file__).resolve().parents[1] / 'Deployment/monitoring/grafana/dashboards'
    for filename, count in [
        ('jurisdigta-errors.json', 1), ('jurisdigta-application-performance.json', 1),
        ('jurisdigta-system-logs.json', 4),
    ]:
        dashboard = json.loads((root / filename).read_text(encoding='utf-8'))
        queries = [t['expr'] for p in dashboard['panels'] for t in p.get('targets', [])]
        assert sum(LOKI_FAILURE_PIPELINE in q for q in queries) == count
        if filename == 'jurisdigta-system-logs.json':
            raw = next(p for p in dashboard['panels'] if p['title'] == 'Recent Logs')
            assert all('line_format' not in t['expr'] for t in raw['targets'])
