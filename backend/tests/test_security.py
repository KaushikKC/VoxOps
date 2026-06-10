"""Tests for HMAC webhook signature verification."""

from __future__ import annotations

import time

import pytest

from app.services.security import (
    SignatureError,
    compute_signature,
    parse_signature_header,
    verify_webhook,
)

SECRET = "shhh"
BODY = b'{"hello":"world"}'


def _header(ts: int, body: bytes = BODY, secret: str = SECRET) -> str:
    return f"t={ts},v0={compute_signature(secret, ts, body)}"


def test_parse_signature_header_ok():
    parsed = parse_signature_header("t=123,v0=abc")
    assert parsed.timestamp == 123
    assert parsed.hash_hex == "abc"


def test_parse_signature_header_missing_parts():
    with pytest.raises(SignatureError):
        parse_signature_header("t=123")


def test_verify_valid_signature():
    now = time.time()
    verify_webhook(
        body=BODY,
        signature_header=_header(int(now)),
        secret=SECRET,
        max_age_seconds=1800,
        now=now,
    )


def test_verify_rejects_tampered_body():
    now = time.time()
    with pytest.raises(SignatureError, match="mismatch"):
        verify_webhook(
            body=b'{"hello":"tampered"}',
            signature_header=_header(int(now)),
            secret=SECRET,
            max_age_seconds=1800,
            now=now,
        )


def test_verify_rejects_wrong_secret():
    now = time.time()
    with pytest.raises(SignatureError):
        verify_webhook(
            body=BODY,
            signature_header=_header(int(now), secret="other"),
            secret=SECRET,
            max_age_seconds=1800,
            now=now,
        )


def test_verify_rejects_old_timestamp():
    now = time.time()
    old = int(now - 4000)
    with pytest.raises(SignatureError, match="too old"):
        verify_webhook(
            body=BODY,
            signature_header=_header(old),
            secret=SECRET,
            max_age_seconds=1800,
            now=now,
        )


def test_verify_requires_secret():
    with pytest.raises(SignatureError, match="not configured"):
        verify_webhook(
            body=BODY,
            signature_header=_header(int(time.time())),
            secret="",
            max_age_seconds=1800,
        )
