from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit


def normalize_line_uri(url: str | None) -> str | None:
    if url is None:
        return None

    candidate = url.strip()
    if not candidate:
        return None

    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https", "line", "tel"}:
        return None
    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        return None

    path = quote(parsed.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parsed.query, safe="=&/%:@!$'()*+,;?-._~")
    fragment = quote(parsed.fragment, safe="=&/%:@!$'()*+,;?-._~")
    return urlunsplit((parsed.scheme, parsed.netloc, path, query, fragment))


def normalize_line_image_url(url: str | None) -> str | None:
    normalized = normalize_line_uri(url)
    if normalized is None:
        return None

    parsed = urlsplit(normalized)
    if parsed.scheme != "https":
        return None

    path = parsed.path.lower()
    if not path.endswith((".jpg", ".jpeg", ".png")):
        return None
    return normalized
