from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

OPTIONAL_WWW_HOSTNAMES = frozenset({"booking.com", "agoda.com"})


def normalize_hostname(hostname: str | None) -> str:
    normalized = (hostname or "").lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def canonicalize_lodging_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlsplit(url.strip())
    hostname = normalize_hostname(parsed.hostname)
    if not parsed.scheme or not hostname:
        return None

    scheme = parsed.scheme.lower()
    netloc = hostname
    if parsed.port is not None and not _is_default_port(scheme, parsed.port):
        netloc = f"{netloc}:{parsed.port}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    return urlunsplit((scheme, netloc, path, "", ""))


def build_lodging_lookup_keys(*urls: str | None) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()

    for url in urls:
        canonical = canonicalize_lodging_url(url)
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        keys.append(canonical)

    return tuple(keys)


def build_equivalent_lodging_url_pattern(url: str | None) -> re.Pattern[str] | None:
    canonical = canonicalize_lodging_url(url)
    if canonical is None:
        return None

    parsed = urlsplit(canonical)
    hostname = parsed.hostname or ""
    escaped_hostname = re.escape(hostname)
    if hostname in OPTIONAL_WWW_HOSTNAMES:
        escaped_hostname = rf"(?:www\.)?{escaped_hostname}"

    path = parsed.path or "/"
    escaped_path = re.escape(path.rstrip("/")) if path != "/" else ""
    trailing_slash_pattern = "/" if path == "/" else "/?"

    return re.compile(
        rf"^{re.escape(parsed.scheme.lower())}://{escaped_hostname}"
        rf"{escaped_path}{trailing_slash_pattern}(?:[?#].*)?$"
    )


def _is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
