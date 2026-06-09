"""Webhook signature verification.

ElevenLabs signs post-call webhooks with an HMAC and sends it in the
``ElevenLabs-Signature`` header using a Stripe-style format::

    t=1739537297,v0=2bf1...e9c

The signed message is ``f"{timestamp}.{raw_body}"`` hashed with HMAC-SHA256 using
the shared webhook secret. Verification is constant-time, and signatures older
than ``webhook_max_age_seconds`` are rejected to prevent replay attacks.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass


class SignatureError(Exception):
    """Raised when a webhook signature is missing, malformed or invalid."""


@dataclass
class ParsedSignature:
    timestamp: int
    hash_hex: str


def parse_signature_header(header: str) -> ParsedSignature:
    """Parse a ``t=...,v0=...`` signature header into its parts."""
    if not header:
        raise SignatureError("missing signature header")

    parts: dict[str, str] = {}
    for segment in header.split(","):
        key, _, value = segment.partition("=")
        parts[key.strip()] = value.strip()

    ts_raw = parts.get("t")
    hash_hex = parts.get("v0")
    if ts_raw is None or hash_hex is None:
        raise SignatureError("signature header missing 't' or 'v0' component")

    try:
        timestamp = int(ts_raw)
    except ValueError as exc:
        raise SignatureError("signature timestamp is not an integer") from exc

    return ParsedSignature(timestamp=timestamp, hash_hex=hash_hex)


def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
    """Compute the expected hex HMAC-SHA256 for a timestamp + body."""
    signed_payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()


def verify_webhook(
    *,
    body: bytes,
    signature_header: str,
    secret: str,
    max_age_seconds: int,
    now: float | None = None,
) -> None:
    """Verify an ElevenLabs webhook signature.

    Raises :class:`SignatureError` on any failure; returns ``None`` on success.
    """
    if not secret:
        raise SignatureError("webhook secret is not configured")

    parsed = parse_signature_header(signature_header)

    current = time.time() if now is None else now
    age = current - parsed.timestamp
    if age > max_age_seconds:
        raise SignatureError(f"signature timestamp too old ({int(age)}s)")
    # Allow small clock skew into the future.
    if age < -300:
        raise SignatureError("signature timestamp is in the future")

    expected = compute_signature(secret, parsed.timestamp, body)
    if not hmac.compare_digest(expected, parsed.hash_hex):
        raise SignatureError("signature mismatch")
