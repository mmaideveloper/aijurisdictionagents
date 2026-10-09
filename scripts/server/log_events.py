"""Privacy-neutral operational classification shared with Loki dashboard filters."""
from __future__ import annotations

import json
import re
from typing import Literal

EventClass = Literal["failure", "retry", "access_denied", "success", "unknown"]

# RE2-compatible: this same pattern is used by the Loki dashboard. Error fields
# alone do not imply failure (Grafana emits error=null in successful INFO logs).
FAILURE_PATTERN = (
    r"(?i)(\blevel[=:]\s*\"?(error|fatal|critical)\b"
    r"|\"level\"\s*:\s*\"(error|fatal|critical)\""
    r"|\|\s*(error|fatal|critical)\s*\|"
    r"|^\s*(error|fatal|critical)\b|^E[0-9]{4}\b"
    r"|\bstatus[=:]\s*\"?(error|failed|failure)\b"
    r"|\"status\"\s*:\s*\"(error|failed|failure)\""
    r"|\bfailed(_laws)?[=:][1-9][0-9]*\b"
    r"|traceback \(most recent call last\)"
    r"|\b[A-Za-z_]+(Error|Exception):"
    r"|\bfailed(\s|$)|\berror_type=[A-Za-z_]+(Error|Exception)\b)"
)
_FAILURE = re.compile(FAILURE_PATTERN)
_RETRY = re.compile(r"\b\w*retry\w*\b", re.I)
_DENIED = re.compile(r'\bstatus_code[\"\s:=]+(?:401|403)\b', re.I)


def classify_line(line: str) -> EventClass:
    if not line.strip():
        return "unknown"
    if _DENIED.search(line):
        # Cannot infer authenticated state from a status code; keep security
        # denials separate, never claim they are all expected/benign.
        if re.search(r"\bauthenticated[=:]true\b", line, re.I):
            return "failure"
        return "access_denied"
    if _FAILURE.search(line):
        return "retry" if _RETRY.search(line) else "failure"
    try:
        record = json.loads(line)
    except (ValueError, TypeError):
        record = None
    if isinstance(record, dict):
        level = str(record.get("level", "")).lower()
        if level in {"info", "debug", "trace"}:
            return "success"
    if re.search(r"\b(level=info|status=ok|status=success|failed_laws=0)\b|\|\s*INFO\s*\|", line, re.I):
        return "success"
    return "unknown"


def event_counts(text: str) -> dict[str, int]:
    counts = {key: 0 for key in ("failure", "retry", "access_denied", "success", "unknown")}
    in_traceback = False
    previous_failure = False
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip() or line in seen:
            continue
        seen.add(line)
        category = classify_line(line)
        start = "Traceback (most recent call last)" in line
        terminal = bool(re.match(r"^[A-Za-z_.]+(?:Error|Exception):", line))
        if in_traceback and terminal:
            in_traceback = False
            continue
        if start:
            if not in_traceback and not previous_failure:
                counts["failure"] += 1
            in_traceback = True
            continue
        if in_traceback and (line.startswith(" ") or line.startswith("During handling")):
            continue
        if category != "unknown":
            in_traceback = False
        counts[category] += 1
        previous_failure = category == "failure"
    return counts
