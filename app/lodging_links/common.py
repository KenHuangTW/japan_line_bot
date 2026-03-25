from __future__ import annotations


def normalize_hostname(hostname: str | None) -> str:
    normalized = (hostname or "").lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized
