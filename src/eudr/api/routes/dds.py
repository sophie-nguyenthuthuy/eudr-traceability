"""Due Diligence Statements: build, submit, fetch."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from eudr.deps import PrincipalDep, SessionDep, require_role
from eudr.errors import ConflictError, NotFoundError
from eudr.models.dds import DDSStatus, DueDiligenceStatement
from eudr.models.user import UserRole
from eudr.schemas.common import Page
from eudr.schemas.dds import DDSCreate, DDSOut, DDSSubmitResponse
from eudr.services.dds_builder import create_dds

router = APIRouter()


@router.get("", response_model=Page[DDSOut])
async def list_dds(
    session: SessionDep,
    _: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[DDSStatus | None, Query(alias="status")] = None,
) -> Page[DDSOut]:
    stmt = select(DueDiligenceStatement)
    if status_filter is not None:
        stmt = stmt.where(DueDiligenceStatement.status == status_filter)
    total = (
        await session.execute(stmt.with_only_columns(func.count(DueDiligenceStatement.id)))
    ).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(DueDiligenceStatement.created_at.desc()).limit(limit).offset(offset),
        )
    ).scalars()
    return Page(
        items=[DDSOut.model_validate(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=DDSOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.EXPORTER, UserRole.ADMIN))],
)
async def build_dds(body: DDSCreate, session: SessionDep) -> DDSOut:
    dds = await create_dds(
        session,
        lot_id=body.lot_id,
        operator_org_id=body.operator_org_id,
        mitigation_measures=body.mitigation_measures,
    )
    return DDSOut.model_validate(dds)


@router.get("/{dds_id}", response_model=DDSOut)
async def get_dds(dds_id: UUID, session: SessionDep, _: PrincipalDep) -> DDSOut:
    dds = (
        await session.execute(
            select(DueDiligenceStatement).where(DueDiligenceStatement.id == dds_id),
        )
    ).scalar_one_or_none()
    if dds is None:
        raise NotFoundError(f"DDS {dds_id} not found")
    return DDSOut.model_validate(dds)


@router.post(
    "/{dds_id}/submit",
    response_model=DDSSubmitResponse,
    dependencies=[Depends(require_role(UserRole.EXPORTER, UserRole.ADMIN))],
)
async def submit_dds(dds_id: UUID, session: SessionDep) -> DDSSubmitResponse:
    dds = (
        await session.execute(
            select(DueDiligenceStatement).where(DueDiligenceStatement.id == dds_id),
        )
    ).scalar_one_or_none()
    if dds is None:
        raise NotFoundError(f"DDS {dds_id} not found")
    if dds.status not in {DDSStatus.READY, DDSStatus.DRAFT}:
        raise ConflictError(f"DDS in status {dds.status.value} cannot be submitted")

    # Lazy-import to avoid pulling celery into route imports for unit tests.
    from eudr.workers.tasks import submit_dds_task

    submit_dds_task.delay(str(dds.id))
    return DDSSubmitResponse(
        dds_id=dds.id,
        status=dds.status,
        queued=True,
        detail="submission enqueued; poll /dds/{id} for status",
    )
