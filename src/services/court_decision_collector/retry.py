"""Durable, bounded retry policy; no source payloads are retained here."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256

import httpx


@dataclass(frozen=True)
class WorkRetry:
    category: str
    next_attempt_at: datetime


def schedule_retry(
    error: Exception, *, attempt: int, reference: str, now: datetime
) -> WorkRetry | None:
    """Only isolate source failures; programming/storage failures must still abort."""
    minimum = 0.0
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in (404, 410):
            category = "source_missing"
        elif status in (408, 429) or status >= 500:
            category = "source_transient"
        else:
            return None
        header = error.response.headers.get("Retry-After", "")
        try:
            minimum = max(0.0, float(header))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(header)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                minimum = max(0.0, (retry_at - now).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    elif isinstance(error, httpx.TransportError):
        category = "source_transient"
    else:
        return None
    # After five attempts defer for operator review, never discard the record.
    if attempt >= 5:
        delay = 7 * 86400 if category == "source_missing" else 86400
    else:
        jitter = int(sha256(reference.encode()).hexdigest()[:4], 16) % 60
        delay = min(3600, 60 * 2 ** max(0, attempt - 1)) + jitter
    return WorkRetry(category, now + timedelta(seconds=max(delay, minimum)))
