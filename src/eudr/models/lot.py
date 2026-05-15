"""Lots: aggregated batches of harvested commodity, the unit a DDS covers."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eudr.models.base import Base, pg_enum
from eudr.models.harvest import Harvest
from eudr.models.organization import Organization
from eudr.models.plot import Commodity


class LotStatus(str, enum.Enum):
    DRAFT = "draft"
    SEALED = "sealed"  # composition frozen
    DDS_PENDING = "dds_pending"
    DDS_SUBMITTED = "dds_submitted"
    SHIPPED = "shipped"
    REJECTED = "rejected"


class Lot(Base):
    __tablename__ = "lots"
    __table_args__ = (
        UniqueConstraint("lot_code", name="lots_lot_code_unique"),
        CheckConstraint("total_quantity_kg > 0", name="lots_quantity_positive"),
    )

    lot_code: Mapped[str] = mapped_column(String(64), nullable=False)
    commodity: Mapped[Commodity] = mapped_column(
        pg_enum(Commodity, "commodity"),
        nullable=False,
        index=True,
    )
    hs_code: Mapped[str] = mapped_column(String(10), nullable=False)
    total_quantity_kg: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    status: Mapped[LotStatus] = mapped_column(
        pg_enum(LotStatus, "lot_status"),
        nullable=False,
        default=LotStatus.DRAFT,
        index=True,
    )
    current_holder_org_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    current_holder: Mapped[Organization] = relationship(lazy="joined")
    compositions: Mapped[list["LotComposition"]] = relationship(
        back_populates="lot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LotComposition(Base):
    """Maps lots to the harvests (and therefore plots) they contain.

    Splitting and merging is modelled as creating new lots with their own
    compositions; the source lot's quantity is decremented via a custody event
    of type ``SPLIT`` or ``MERGE``.
    """

    __tablename__ = "lot_compositions"
    __table_args__ = (
        UniqueConstraint("lot_id", "harvest_id", name="lot_compositions_unique"),
        CheckConstraint("quantity_kg > 0", name="lot_compositions_quantity_positive"),
    )

    lot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    harvest_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("harvests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity_kg: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)

    lot: Mapped[Lot] = relationship(back_populates="compositions")
    harvest: Mapped[Harvest] = relationship(lazy="joined")
