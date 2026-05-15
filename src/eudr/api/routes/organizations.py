"""Organization CRUD (admin-only writes)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from eudr.deps import PrincipalDep, SessionDep, require_role
from eudr.errors import NotFoundError
from eudr.models.organization import Organization
from eudr.models.user import UserRole
from eudr.schemas.common import Page
from eudr.schemas.organization import OrganizationCreate, OrganizationOut

router = APIRouter()


@router.get("", response_model=Page[OrganizationOut])
async def list_organizations(
    session: SessionDep,
    _: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[OrganizationOut]:
    total = (await session.execute(select(func.count(Organization.id)))).scalar_one()
    rows = (
        await session.execute(
            select(Organization)
            .order_by(Organization.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return Page(
        items=[OrganizationOut.model_validate(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=OrganizationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def create_organization(body: OrganizationCreate, session: SessionDep) -> OrganizationOut:
    org = Organization(**body.model_dump())
    session.add(org)
    await session.flush()
    return OrganizationOut.model_validate(org)


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(org_id: UUID, session: SessionDep, _: PrincipalDep) -> OrganizationOut:
    org = (
        await session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        raise NotFoundError(f"organization {org_id} not found")
    return OrganizationOut.model_validate(org)
