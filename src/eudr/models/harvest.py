"""Harvests: a quantity of commodity extracted from a specific plot on a given date."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eudr.models.base import Base
from eudr.models.plot import Plot


class Harvest(Base):
    __tablename__ = "harvests"
    __table_args__ = (
        CheckConstraint("quantity_kg > 0", name="harvests_quantity_positive"),
    )

    plot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity_kg: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    harvest_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(128), index=True)

    plot: Mapped[Plot] = relationship(lazy="joined")
