from __future__ import annotations

import base64
import hashlib
import hmac


def generate_signature(channel_secret: str, body: bytes) -> str:
    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def verify_signature(
    channel_secret: str,
    body: bytes,
    signature: str | None,
) -> bool:
    if not signature:
        return False
    expected_signature = generate_signature(channel_secret, body)
    return hmac.compare_digest(expected_signature, signature.strip())
