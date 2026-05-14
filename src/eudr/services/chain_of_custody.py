"""Chain-of-custody event recording with a per-lot hash chain.

Every event for a lot includes ``prev_hash`` pointing at the previous event's
``event_hash``, plus an ``event_hash`` computed as ``sha256(prev_hash ||
canonical_json(event_payload))``. Tampering with any event invalidates every
subsequent hash, giving auditors a cheap integrity check.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eudr.errors import NotFoundError, ValidationError
from eudr.models.custody import CustodyEvent, CustodyEventType
from eudr.models.lot import Lot
from eudr.services.geo import geom_to_db


def _canonical(event: dict[str, Any]) -> bytes:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), default=str).encode()


def _hash(prev: str | None, event: dict[str, Any]) -> str:
    h = hashlib.sha256()
    if prev:
        h.update(prev.encode())
    h.update(_canonical(event))
    return h.hexdigest()


async def _latest_event_hash(session: AsyncSession, lot_id: UUID) -> str | None:
    stmt = (
        select(CustodyEvent.event_hash)
        .where(CustodyEvent.lot_id == lot_id)
        .order_by(CustodyEvent.occurred_at.desc(), CustodyEvent.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def record_event(
    session: AsyncSession,
    *,
    lot_id: UUID,
    event_type: CustodyEventType,
    occurred_at: datetime,
    recorded_by_user_id: UUID,
    from_org_id: UUID | None = None,
    to_org_id: UUID | None = None,
    location: BaseGeometry | None = None,
    document_url: str | None = None,
    payload: dict[str, Any] | None = None,
) -> CustodyEvent:
    """Insert a custody event and link it into the per-lot hash chain.

    For TRANSFER and SPLIT/MERGE events ``to_org_id`` becomes the lot's new
    current holder.
    """
    lot = (await session.execute(select(Lot).where(Lot.id == lot_id))).scalar_one_or_none()
    if lot is None:
        raise NotFoundError(f"lot {lot_id} not found")
    if event_type is CustodyEventType.TRANSFER and (from_org_id is None or to_org_id is None):
        raise ValidationError("transfer events require both from_org_id and to_org_id")

    prev_hash = await _latest_event_hash(session, lot_id)
    canonical_payload = {
        "lot_id": str(lot_id),
        "event_type": event_type.value,
        "from_org_id": str(from_org_id) if from_org_id else None,
        "to_org_id": str(to_org_id) if to_org_id else None,
        "occurred_at": occurred_at.isoformat(),
        "location": mapping(location) if location is not None else None,
        "document_url": document_url,
        "payload": payload or {},
    }
    event_hash = _hash(prev_hash, canonical_payload)

    event = CustodyEvent(
        lot_id=lot_id,
        event_type=event_type,
        from_org_id=from_org_id,
        to_org_id=to_org_id,
        occurred_at=occurred_at,
        location=geom_to_db(location) if location is not None else None,
        document_url=document_url,
        payload=payload or {},
        prev_hash=prev_hash,
        event_hash=event_hash,
        recorded_by_user_id=recorded_by_user_id,
    )
    session.add(event)

    if event_type in {CustodyEventType.TRANSFER, CustodyEventType.SPLIT, CustodyEventType.MERGE}:
        if to_org_id is not None:
            lot.current_holder_org_id = to_org_id

    await session.flush()
    return event


async def verify_chain(session: AsyncSession, lot_id: UUID) -> tuple[bool, int]:
    """Re-hashes every event for the lot in order. Returns ``(ok, count)``."""
    stmt = (
        select(CustodyEvent)
        .where(CustodyEvent.lot_id == lot_id)
        .order_by(CustodyEvent.occurred_at.asc(), CustodyEvent.created_at.asc())
    )
    events = list((await session.execute(stmt)).scalars())
    prev_hash: str | None = None
    for ev in events:
        canonical_payload = {
            "lot_id": str(ev.lot_id),
            "event_type": ev.event_type.value,
            "from_org_id": str(ev.from_org_id) if ev.from_org_id else None,
            "to_org_id": str(ev.to_org_id) if ev.to_org_id else None,
            "occurred_at": ev.occurred_at.isoformat(),
            "location": None
            if ev.location is None
            else mapping(__import__("geoalchemy2.shape", fromlist=["to_shape"]).to_shape(ev.location)),
            "document_url": ev.document_url,
            "payload": ev.payload,
        }
        expected = _hash(prev_hash, canonical_payload)
        if expected != ev.event_hash or ev.prev_hash != prev_hash:
            return False, len(events)
        prev_hash = ev.event_hash
    return True, len(events)
