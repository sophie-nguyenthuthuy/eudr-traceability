"""Chain-of-custody event recording and verification."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from eudr.deps import CurrentUserDep, PrincipalDep, SessionDep
from eudr.models.custody import CustodyEvent
from eudr.schemas.common import Page
from eudr.schemas.custody import CustodyEventCreate, CustodyEventOut
from eudr.services.chain_of_custody import record_event, verify_chain
from eudr.services.geo import geom_from_db, parse_geojson

router = APIRouter()


def _to_out(event: CustodyEvent) -> CustodyEventOut:
    return CustodyEventOut.model_validate(
        {
            "id": event.id,
            "created_at": event.created_at,
            "updated_at": event.updated_at,
            "lot_id": event.lot_id,
            "event_type": event.event_type,
            "from_org_id": event.from_org_id,
            "to_org_id": event.to_org_id,
            "occurred_at": event.occurred_at,
            "location": geom_from_db(event.location),
            "document_url": event.document_url,
            "payload": event.payload,
            "prev_hash": event.prev_hash,
            "event_hash": event.event_hash,
            "recorded_by_user_id": event.recorded_by_user_id,
        },
    )


@router.get("/lots/{lot_id}/events", response_model=Page[CustodyEventOut])
async def list_events(
    lot_id: UUID,
    session: SessionDep,
    _: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CustodyEventOut]:
    stmt = select(CustodyEvent).where(CustodyEvent.lot_id == lot_id)
    total = (
        await session.execute(stmt.with_only_columns(func.count(CustodyEvent.id)))
    ).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(CustodyEvent.occurred_at.asc()).limit(limit).offset(offset),
        )
    ).scalars()
    return Page(
        items=[_to_out(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post("/events", response_model=CustodyEventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: CustodyEventCreate,
    session: SessionDep,
    user: CurrentUserDep,
) -> CustodyEventOut:
    location = parse_geojson(body.location) if body.location else None
    event = await record_event(
        session,
        lot_id=body.lot_id,
        event_type=body.event_type,
        occurred_at=body.occurred_at,
        recorded_by_user_id=user.id,
        from_org_id=body.from_org_id,
        to_org_id=body.to_org_id,
        location=location,
        document_url=body.document_url,
        payload=body.payload,
    )
    return _to_out(event)


@router.get("/lots/{lot_id}/verify")
async def verify(lot_id: UUID, session: SessionDep, _: PrincipalDep) -> dict:
    ok, count = await verify_chain(session, lot_id)
    return {"lot_id": str(lot_id), "ok": ok, "event_count": count}
