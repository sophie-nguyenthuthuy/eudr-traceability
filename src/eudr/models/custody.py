"""Chain-of-custody events.

Every custody event is immutable once written. A cryptographic signature
(``signature``) is computed over a canonical JSON serialization of the event
plus a hash chain of the previous event for the same lot (``prev_hash``),
giving an append-only, tamper-evident chain per lot.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eudr.models.base import Base
from eudr.models.lot import Lot
from eudr.models.organization import Organization


class CustodyEventType(str, enum.Enum):
    TRANSFER = "transfer"  # custody handover, no transformation
    TRANSFORMATION = "transformation"  # processing (drying, hulling, milling, ...)
    TRANSPORT = "transport"  # in-transit checkpoint
    SPLIT = "split"  # one lot becomes multiple
    MERGE = "merge"  # multiple lots become one
    INSPECTION = "inspection"  # auditor / third-party check


class CustodyEvent(Base):
    __tablename__ = "custody_events"
    __table_args__ = (
        Index("custody_events_lot_occurred_at_idx", "lot_id", "occurred_at"),
    )

    lot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[CustodyEventType] = mapped_column(
        Enum(CustodyEventType, name="custody_event_type"),
        nullable=False,
    )
    from_org_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
    )
    to_org_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
    )
    document_url: Mapped[str | None] = mapped_column(String(1024))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    prev_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    event_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    signature: Mapped[str | None] = mapped_column(String(512))
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    lot: Mapped[Lot] = relationship(lazy="joined")
    from_org: Mapped[Organization | None] = relationship(
        foreign_keys=[from_org_id], lazy="joined"
    )
    to_org: Mapped[Organization | None] = relationship(
        foreign_keys=[to_org_id], lazy="joined"
    )
