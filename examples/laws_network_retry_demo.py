"""Offline example: python examples/laws_network_retry_demo.py."""
import socket
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from urllib.error import URLError
from urllib.request import Request

from services.laws_collector.network_retry import open_with_retry

if __name__ == '__main__':
    calls = []

    def synthetic_opener(request, *, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise URLError(socket.gaierror(socket.EAI_AGAIN, 'synthetic temporary DNS failure'))
        return 'synthetic resource'

    assert open_with_retry(Request('https://source.invalid'), timeout=10,
                           opener=synthetic_opener) == 'synthetic resource'
    assert len(calls) == 2
    print('Temporary DNS recovery within original deadline: PASS')
