from email.message import Message
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request
from types import SimpleNamespace

import pytest

from services.laws_collector import network_retry
from services.laws_collector.slovlex_live_source import _fetch_resource
from services.laws_collector.slovlex_process import SlovLexSequentialImportRunner
from services.laws_collector.import_planner import SlovLexImportPlanner


@pytest.fixture(autouse=True)
def offline_clock(monkeypatch):
    elapsed = [0.0]
    monkeypatch.setattr(network_retry.time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(network_retry.time, 'sleep', lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    monkeypatch.setattr(network_retry.random, 'uniform', lambda a, b: 0.0)
    return elapsed


def test_temporary_dns_failure_recovers_within_original_deadline():
    calls = []
    response = object()

    def opener(request, *, timeout):
        calls.append(timeout)
        if len(calls) < 3:
            raise URLError(socket.gaierror(socket.EAI_AGAIN, 'synthetic DNS failure'))
        return response

    assert network_retry.open_with_retry(Request('https://source.invalid'), timeout=10, opener=opener) is response
    assert calls == [10, 9, 7]


@pytest.mark.parametrize('error', [
    URLError(socket.gaierror(socket.EAI_NONAME, 'synthetic invalid host')),
    HTTPError('https://source.invalid', 404, 'missing', None, None),
    HTTPError('https://source.invalid', 403, 'denied', None, None),
    ValueError('synthetic programming failure'),
])
def test_permanent_http_dns_and_programming_failures_are_not_retried(error):
    calls = []

    def opener(request, *, timeout):
        calls.append(timeout)
        raise error

    with pytest.raises(type(error)):
        network_retry.open_with_retry(Request('https://source.invalid'), timeout=10, opener=opener)
    assert len(calls) == 1


def test_persistent_transient_failure_is_visible_after_three_attempts():
    calls = []

    def opener(request, *, timeout):
        calls.append(timeout)
        raise URLError(socket.gaierror(socket.EAI_AGAIN, 'synthetic failure'))

    with pytest.raises(URLError):
        network_retry.open_with_retry(Request('https://source.invalid'), timeout=10, opener=opener)
    assert len(calls) == 3


def test_retry_after_longer_than_deadline_is_not_ignored(offline_clock):
    headers = Message()
    headers['Retry-After'] = '120'

    def opener(request, *, timeout):
        raise HTTPError('https://source.invalid', 429, 'rate limited', headers, None)

    with pytest.raises(HTTPError):
        network_retry.open_with_retry(Request('https://source.invalid'), timeout=10, opener=opener)
    assert offline_clock[0] == 0


def test_live_snapshot_fetch_uses_dns_recovery_without_fabricating_content(monkeypatch):
    calls = []

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'synthetic legal resource'

    def opener(request, *, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise URLError(socket.gaierror(socket.EAI_AGAIN, 'synthetic failure'))
        return Response()

    monkeypatch.setattr('services.laws_collector.slovlex_live_source.urlopen', opener)
    result = _fetch_resource(url='https://source.invalid', timeout_seconds=10)
    assert result.body == b'synthetic legal resource'
    assert len(calls) == 2


def test_exhausted_http_failure_does_not_advance_law_cursor(monkeypatch):
    config = SimpleNamespace(country_code='SK')
    planner = SlovLexImportPlanner(config=config)
    initial = planner.initial_progress()

    class Store:
        saves = 0

        def get_or_create_collector_progress(self, **kwargs):
            return initial

        def save_collector_progress(self, progress):
            self.saves += 1

    def opener(request, *, timeout):
        raise HTTPError('https://source.invalid', 503, 'unavailable', None, None)

    monkeypatch.setattr('services.laws_collector.slovlex_process.urlopen', opener)
    store = Store()
    runner = SlovLexSequentialImportRunner(config=config, store=store, planner=planner)
    with pytest.raises(RuntimeError, match='unavailable: HTTP 503'):
        runner.run(max_probes=1)
    assert store.saves == 0


def test_only_confirmed_404_is_a_missing_resource(monkeypatch):
    from services.laws_collector.import_planner import ImportTarget

    def opener(request, *, timeout):
        raise HTTPError('https://source.invalid', 404, 'missing', None, None)

    monkeypatch.setattr('services.laws_collector.slovlex_process.urlopen', opener)
    runner = SlovLexSequentialImportRunner(config=SimpleNamespace(country_code='SK'), store=object())
    result = runner._probe_target(target=ImportTarget(2026, 1), timeout_seconds=10)
    assert not result.exists
    assert result.status_code == 404
