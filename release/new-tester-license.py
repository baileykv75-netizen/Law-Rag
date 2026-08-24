from __future__ import annotations

import argparse
import base64
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCHEMA_VERSION = "1.0.0"
AUDIENCE = "law-rag-limited-test"
DEFAULT_RELEASE_LABEL = "0.8.0-rc3-tester2"
TOKEN_PREFIX = "LR1"
_TESTER_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_RELEASE_RE = re.compile(r"^\d+\.\d+\.\d+-rc\d+-tester\d+$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_utc(value: str, label: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError(f"{label} must be RFC3339 UTC ending in Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    data = path.read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("private key must be an Ed25519 PEM key")
    return key


def issue_license(
    *,
    private_key: Ed25519PrivateKey,
    tester_id: str,
    release_label: str,
    not_before: datetime,
    expires_at: datetime,
) -> tuple[str, dict[str, str]]:
    if not _TESTER_ID_RE.fullmatch(tester_id):
        raise ValueError("tester-id must use only letters, digits, dot, underscore or hyphen (1-64 chars)")
    if not _RELEASE_RE.fullmatch(release_label):
        raise ValueError("release-label must look like 0.8.0-rc3-tester2")
    if expires_at <= not_before:
        raise ValueError("expires-at must be later than not-before")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "audience": AUDIENCE,
        "license_id": str(uuid4()),
        "tester_id": tester_id,
        "release_label": release_label,
        "not_before_utc": _format_utc(not_before),
        "expires_at_utc": _format_utc(expires_at),
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(payload_bytes)
    token = f"{TOKEN_PREFIX}.{_b64url(payload_bytes)}.{_b64url(signature)}"
    return token, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue an offline signed Law-Rag limited tester license.")
    parser.add_argument("--private-key", type=Path, required=True, help="Owner-only Ed25519 private PEM key. Never send it to testers.")
    parser.add_argument("--tester-id", required=True, help="Traceable tester alias such as T001 or OWNER-TEST.")
    parser.add_argument("--release-label", default=DEFAULT_RELEASE_LABEL)
    parser.add_argument("--not-before", help="Optional RFC3339 UTC timestamp ending in Z. Defaults to current UTC time.")
    expiry = parser.add_mutually_exclusive_group()
    expiry.add_argument("--days", type=int, help="Validity length in days. Defaults to 7 when --expires-at is omitted.")
    expiry.add_argument("--expires-at", help="Explicit RFC3339 UTC expiry ending in Z.")
    parser.add_argument("--output", type=Path, required=True, help="Output .license.txt path.")
    parser.add_argument("--receipt", type=Path, help="Optional non-secret JSON issuance receipt path.")
    args = parser.parse_args()

    try:
        if not args.private_key.is_file():
            raise ValueError(f"private key does not exist: {args.private_key}")
        not_before = _parse_utc(args.not_before, "--not-before") if args.not_before else _utc_now()
        if args.expires_at:
            expires_at = _parse_utc(args.expires_at, "--expires-at")
        else:
            days = 7 if args.days is None else args.days
            if not 1 <= days <= 365:
                raise ValueError("--days must be between 1 and 365")
            expires_at = not_before + timedelta(days=days)

        token, payload = issue_license(
            private_key=_load_private_key(args.private_key),
            tester_id=args.tester_id,
            release_label=args.release_label,
            not_before=not_before,
            expires_at=expires_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(token + "\n", encoding="utf-8")
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt = {
                **payload,
                "token_format": "LR1.Ed25519",
                "private_key_embedded": False,
                "tester_receives_private_key": False,
            }
            args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))

    print(f"Issued tester license: {args.output}")
    print(f"Tester ID: {payload['tester_id']}")
    print(f"Release: {payload['release_label']}")
    print(f"Expires UTC: {payload['expires_at_utc']}")
    print("Private key was not written to the license token or receipt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
