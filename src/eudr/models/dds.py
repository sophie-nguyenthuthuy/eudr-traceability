"""Due Diligence Statement (DDS) – the artefact submitted to EU TRACES NT."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eudr.models.base import Base
from eudr.models.lot import Lot
from eudr.models.organization import Organization


class DDSStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class DueDiligenceStatement(Base):
    __tablename__ = "due_diligence_statements"
    __table_args__ = (
        UniqueConstraint("dds_reference", name="dds_reference_unique"),
    )

    lot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operator_org_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    dds_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DDSStatus] = mapped_column(
        Enum(DDSStatus, name="dds_status"),
        nullable=False,
        default=DDSStatus.DRAFT,
        index=True,
    )
    traces_nt_reference: Mapped[str | None] = mapped_column(String(64), unique=True)
    traces_nt_verification_number: Mapped[str | None] = mapped_column(String(64))

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(2048))

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    risk_assessment: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    mitigation_measures: Mapped[str | None] = mapped_column(String(4096))

    lot: Mapped[Lot] = relationship(lazy="joined")
    operator: Mapped[Organization] = relationship(lazy="joined")
