from __future__ import annotations

import os


def _read_minutes(name: str) -> int:
    value = int(os.getenv(name, "0"))
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _describe(name: str) -> str:
    minutes = _read_minutes(name)
    if minutes == 0:
        return f"{name}=0 (unlimited)"
    return f"{name}={minutes} minute(s)"


def main() -> int:
    print(_describe("LAWS_COLLECTOR_MAX_RUNNING_TIME"))
    print(_describe("DOCUMENT_PROCESSOR_MAX_RUNNING_TIME"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
