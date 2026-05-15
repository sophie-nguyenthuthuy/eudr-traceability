"""Harvest registration."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from eudr.deps import PrincipalDep, SessionDep, require_role
from eudr.errors import NotFoundError
from eudr.models.harvest import Harvest
from eudr.models.plot import Plot
from eudr.models.user import UserRole
from eudr.schemas.common import Page
from eudr.schemas.harvest import HarvestCreate, HarvestOut

router = APIRouter()


@router.get("", response_model=Page[HarvestOut])
async def list_harvests(
    session: SessionDep,
    _: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    plot_id: UUID | None = None,
) -> Page[HarvestOut]:
    stmt = select(Harvest)
    if plot_id is not None:
        stmt = stmt.where(Harvest.plot_id == plot_id)
    total = (await session.execute(stmt.with_only_columns(func.count(Harvest.id)))).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(Harvest.harvest_date.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    return Page(
        items=[HarvestOut.model_validate(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=HarvestOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_role(
                UserRole.PRODUCER,
                UserRole.COOPERATIVE_OFFICER,
                UserRole.ADMIN,
            ),
        ),
    ],
)
async def create_harvest(body: HarvestCreate, session: SessionDep) -> HarvestOut:
    plot = (await session.execute(select(Plot).where(Plot.id == body.plot_id))).scalar_one_or_none()
    if plot is None:
        raise NotFoundError(f"plot {body.plot_id} not found")
    harvest = Harvest(**body.model_dump())
    session.add(harvest)
    await session.flush()
    return HarvestOut.model_validate(harvest)
