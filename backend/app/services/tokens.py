from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any


def encode_access_token(
    subject: str,
    secret_key: str,
    expires_minutes: int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "exp": int(expires_at.timestamp()),
        **(extra_claims or {}),
    }
    signing_input = ".".join([_base64url_json(header), _base64url_json(payload)])
    signature = _sign(signing_input, secret_key)
    return f"{signing_input}.{signature}"


def decode_access_token(token: str, secret_key: str) -> dict[str, Any] | None:
    try:
        header_part, payload_part, signature = token.split(".", 2)
    except ValueError:
        return None

    signing_input = f"{header_part}.{payload_part}"
    expected_signature = _sign(signing_input, secret_key)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = _base64url_decode_json(payload_part)
    except (ValueError, json.JSONDecodeError):
        return None
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(datetime.now(UTC).timestamp()):
        return None

    return payload


def _base64url_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode_json(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("Token payload must be an object.")
    return payload


def _sign(value: str, secret_key: str) -> str:
    digest = hmac.new(secret_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
