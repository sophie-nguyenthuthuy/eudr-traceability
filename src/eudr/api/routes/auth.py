"""Login and token refresh."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from eudr.deps import CurrentUserDep, SessionDep
from eudr.errors import AuthError
from eudr.models.user import User
from eudr.schemas.auth import CurrentUser, LoginRequest, RefreshRequest, TokenPair
from eudr.security import (
    decode_token,
    issue_access_token,
    issue_refresh_token,
    verify_password,
)

router = APIRouter()


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, session: SessionDep) -> TokenPair:
    user = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if user is None or user.disabled_at is not None:
        raise AuthError("invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise AuthError("invalid credentials")

    access, access_exp = issue_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role.value,
    )
    refresh, refresh_exp = issue_refresh_token(
        user_id=user.id,
        organization_id=user.organization_id,
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: SessionDep) -> TokenPair:
    claims = decode_token(body.refresh_token, expected_type="refresh")
    user = (
        await session.execute(select(User).where(User.id == claims["sub"]))
    ).scalar_one_or_none()
    if user is None or user.disabled_at is not None:
        raise AuthError("user not found")
    access, access_exp = issue_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role.value,
    )
    new_refresh, refresh_exp = issue_refresh_token(
        user_id=user.id,
        organization_id=user.organization_id,
    )
    return TokenPair(
        access_token=access,
        refresh_token=new_refresh,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )


@router.get("/me", response_model=CurrentUser, status_code=status.HTTP_200_OK)
async def me(user: CurrentUserDep) -> CurrentUser:
    return CurrentUser.model_validate(user)
