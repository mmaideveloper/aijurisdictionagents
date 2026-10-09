"""Bounded recovery from transient DNS/transport and upstream HTTP failures."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
import socket
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request


def _is_transient(error: Exception) -> bool:
    if isinstance(error, HTTPError):
        return error.code in (408, 429) or 500 <= error.code < 600
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, socket.gaierror):
        return reason.errno == socket.EAI_AGAIN
    return isinstance(reason, (TimeoutError, ConnectionError))


def _retry_after(error: Exception) -> float:
    if not isinstance(error, HTTPError) or error.headers is None:
        return 0.0
    header = error.headers.get("Retry-After", "")
    try:
        return max(0.0, float(header))
    except ValueError:
        try:
            timestamp = parsedate_to_datetime(header)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return max(0.0, (timestamp - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0.0


def open_with_retry(
    request: Request, *, timeout: float, opener: Callable[..., Any],
) -> Any:
    """At most three opens within the original deadline; never retry local I/O."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    deadline = time.monotonic() + timeout
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Source request deadline exhausted")
        try:
            return opener(request, timeout=remaining)
        except (URLError, TimeoutError, ConnectionError) as error:
            if attempt == 2 or not _is_transient(error):
                raise
            delay = max(2 ** attempt + random.uniform(0, 0.25), _retry_after(error))
            if delay >= deadline - time.monotonic():
                # Preserve the failure; do not violate Retry-After or claim absence.
                raise
            time.sleep(delay)
    raise RuntimeError("unreachable retry state")
