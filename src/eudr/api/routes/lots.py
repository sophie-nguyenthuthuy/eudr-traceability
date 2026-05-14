"""Lot composition and lifecycle."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from eudr.deps import PrincipalDep, SessionDep, require_role
from eudr.errors import ConflictError, NotFoundError, ValidationError
from eudr.models.harvest import Harvest
from eudr.models.lot import Lot, LotComposition, LotStatus
from eudr.models.user import UserRole
from eudr.schemas.common import Page
from eudr.schemas.lot import LotCompositionOut, LotCreate, LotOut

router = APIRouter()


def _to_out(lot: Lot) -> LotOut:
    return LotOut.model_validate(
        {
            "id": lot.id,
            "created_at": lot.created_at,
            "updated_at": lot.updated_at,
            "lot_code": lot.lot_code,
            "commodity": lot.commodity,
            "hs_code": lot.hs_code,
            "total_quantity_kg": float(lot.total_quantity_kg),
            "status": lot.status,
            "current_holder_org_id": lot.current_holder_org_id,
            "compositions": [
                LotCompositionOut.model_validate(
                    {
                        "id": c.id,
                        "created_at": c.created_at,
                        "updated_at": c.updated_at,
                        "harvest_id": c.harvest_id,
                        "quantity_kg": float(c.quantity_kg),
                    },
                )
                for c in lot.compositions
            ],
        },
    )


@router.get("", response_model=Page[LotOut])
async def list_lots(
    session: SessionDep,
    _: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[LotOut]:
    total = (await session.execute(select(func.count(Lot.id)))).scalar_one()
    rows = (
        await session.execute(
            select(Lot).order_by(Lot.created_at.desc()).limit(limit).offset(offset),
        )
    ).scalars()
    return Page(
        items=[_to_out(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=LotOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_role(
                UserRole.COOPERATIVE_OFFICER,
                UserRole.EXPORTER,
                UserRole.ADMIN,
            ),
        ),
    ],
)
async def create_lot(body: LotCreate, session: SessionDep) -> LotOut:
    # Validate every referenced harvest exists, all the same commodity,
    # and that we are not over-drawing a harvest's available quantity.
    harvest_ids = [c.harvest_id for c in body.compositions]
    harvests = list(
        (
            await session.execute(select(Harvest).where(Harvest.id.in_(harvest_ids)))
        ).scalars(),
    )
    if len(harvests) != len(harvest_ids):
        missing = set(harvest_ids) - {h.id for h in harvests}
        raise NotFoundError(f"unknown harvest ids: {sorted(map(str, missing))}")

    # Sum of already-allocated quantities per harvest.
    existing = dict(
        (
            await session.execute(
                select(
                    LotComposition.harvest_id,
                    func.coalesce(func.sum(LotComposition.quantity_kg), 0),
                )
                .where(LotComposition.harvest_id.in_(harvest_ids))
                .group_by(LotComposition.harvest_id),
            )
        ).all(),
    )
    by_id = {h.id: h for h in harvests}
    for comp in body.compositions:
        h = by_id[comp.harvest_id]
        allocated = Decimal(existing.get(h.id, 0))
        available = Decimal(h.quantity_kg) - allocated
        if Decimal(str(comp.quantity_kg)) > available:
            raise ConflictError(
                f"harvest {h.id} has {available} kg available, "
                f"requested {comp.quantity_kg} kg",
            )

    total = sum(Decimal(str(c.quantity_kg)) for c in body.compositions)
    if total <= 0:
        raise ValidationError("lot total quantity must be > 0")

    lot = Lot(
        lot_code=body.lot_code,
        commodity=body.commodity,
        hs_code=body.hs_code,
        total_quantity_kg=float(total),
        status=LotStatus.DRAFT,
        current_holder_org_id=body.current_holder_org_id,
        compositions=[
            LotComposition(harvest_id=c.harvest_id, quantity_kg=c.quantity_kg)
            for c in body.compositions
        ],
    )
    session.add(lot)
    await session.flush()
    return _to_out(lot)


@router.post("/{lot_id}/seal", response_model=LotOut)
async def seal_lot(lot_id: UUID, session: SessionDep, _: PrincipalDep) -> LotOut:
    lot = (await session.execute(select(Lot).where(Lot.id == lot_id))).scalar_one_or_none()
    if lot is None:
        raise NotFoundError(f"lot {lot_id} not found")
    if lot.status != LotStatus.DRAFT:
        raise ConflictError(f"lot is in status {lot.status.value}, cannot seal")
    lot.status = LotStatus.SEALED
    await session.flush()
    return _to_out(lot)


@router.get("/{lot_id}", response_model=LotOut)
async def get_lot(lot_id: UUID, session: SessionDep, _: PrincipalDep) -> LotOut:
    lot = (await session.execute(select(Lot).where(Lot.id == lot_id))).scalar_one_or_none()
    if lot is None:
        raise NotFoundError(f"lot {lot_id} not found")
    return _to_out(lot)
