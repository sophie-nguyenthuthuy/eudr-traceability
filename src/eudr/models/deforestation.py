"""Deforestation checks performed against remote-sensing data sources."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eudr.models.base import Base, pg_enum
from eudr.models.plot import Plot


class DeforestationSource(str, enum.Enum):
    HANSEN_GFC = "hansen_gfc"  # Hansen Global Forest Change (UMD)
    JRC_TMF = "jrc_tmf"  # JRC Tropical Moist Forest
    NATIONAL_FOREST_MAP = "national_forest_map"  # VN MARD forest map
    MANUAL = "manual"  # auditor-attested


class DeforestationCheck(Base):
    __tablename__ = "deforestation_checks"

    plot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[DeforestationSource] = mapped_column(
        pg_enum(DeforestationSource, "deforestation_source"),
        nullable=False,
    )
    cutoff_date: Mapped[date] = mapped_column(Date, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    overlap_ha: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    risk_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(2048))
    raw_result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    plot: Mapped[Plot] = relationship(lazy="joined")
