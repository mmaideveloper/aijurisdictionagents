from __future__ import annotations


def is_slovakia(country: str) -> bool:
    if not country:
        return False
    normalized = country.strip().lower()
    return normalized in {"sk", "svk", "slovakia", "slovak republic"}
