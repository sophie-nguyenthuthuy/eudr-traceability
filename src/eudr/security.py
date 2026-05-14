"""JWT issuance and verification, plus password hashing.

We use RS256 so the public key can be distributed to other services for
verification without sharing the signing key. Tokens carry the user id,
organization id, and role.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from eudr.config import get_settings
from eudr.errors import AuthError

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "RS256"


def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd_ctx.verify(password, hashed)


def _now() -> datetime:
    return datetime.now(UTC)


def issue_access_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    """Returns (token, expires_at)."""
    settings = get_settings()
    expires_at = _now() + timedelta(seconds=settings.jwt_access_ttl_seconds)
    claims: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role,
        "iat": int(_now().timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": "access",
        **(extra_claims or {}),
    }
    token = jwt.encode(claims, settings.jwt_private_key, algorithm=ALGORITHM)
    return token, expires_at


def issue_refresh_token(*, user_id: UUID, organization_id: UUID) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = _now() + timedelta(seconds=settings.jwt_refresh_ttl_seconds)
    claims = {
        "iss": settings.jwt_issuer,
        "sub": str(user_id),
        "org": str(organization_id),
        "iat": int(_now().timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": "refresh",
    }
    token = jwt.encode(claims, settings.jwt_private_key, algorithm=ALGORITHM)
    return token, expires_at


def decode_token(token: str, *, expected_type: str = "access") -> dict[str, Any]:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
        )
    except JWTError as e:  # noqa: BLE001
        raise AuthError(f"invalid token: {e}") from e
    if claims.get("type") != expected_type:
        raise AuthError(f"expected {expected_type} token, got {claims.get('type')}")
    return claims
