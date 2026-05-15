"""FastAPI dependencies: current user, current org, role enforcement."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eudr.db import get_session
from eudr.errors import AuthError, ForbiddenError
from eudr.models.user import User, UserRole
from eudr.security import decode_token


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    role: UserRole


async def _principal_from_header(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    claims = decode_token(token)
    try:
        return Principal(
            user_id=UUID(claims["sub"]),
            organization_id=UUID(claims["org"]),
            role=UserRole(claims["role"]),
        )
    except (KeyError, ValueError) as e:  # noqa: BLE001
        raise AuthError("malformed token claims") from e


async def get_current_user(
    principal: Annotated[Principal, Depends(_principal_from_header)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None or user.disabled_at is not None:
        raise AuthError("user not found or disabled")
    return user


def require_role(*allowed: UserRole) -> Callable[..., Awaitable[Principal]]:
    """Dependency factory: enforces that the principal has one of the given roles."""

    async def _check(
        principal: Annotated[Principal, Depends(_principal_from_header)],
    ) -> Principal:
        if principal.role not in allowed:
            raise ForbiddenError(
                f"role {principal.role.value!r} not allowed; need one of "
                f"{[r.value for r in allowed]}",
            )
        return principal

    return _check


SessionDep = Annotated[AsyncSession, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(_principal_from_header)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
