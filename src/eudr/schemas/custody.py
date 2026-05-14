"""Custody event schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from eudr.models.custody import CustodyEventType
from eudr.schemas.common import GeoJSONGeometry, TimestampedID


class CustodyEventCreate(BaseModel):
    lot_id: UUID
    event_type: CustodyEventType
    from_org_id: UUID | None = None
    to_org_id: UUID | None = None
    occurred_at: datetime
    location: GeoJSONGeometry | None = Field(
        default=None,
        description="Optional POINT geometry where the event occurred.",
    )
    document_url: str | None = Field(default=None, max_length=1024)
    payload: dict = Field(default_factory=dict)


class CustodyEventOut(TimestampedID):
    lot_id: UUID
    event_type: CustodyEventType
    from_org_id: UUID | None
    to_org_id: UUID | None
    occurred_at: datetime
    location: GeoJSONGeometry | None
    document_url: str | None
    payload: dict
    prev_hash: str | None
    event_hash: str
    recorded_by_user_id: UUID
