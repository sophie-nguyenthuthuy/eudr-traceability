"""Plots of land: the unit EUDR cares about most.

Per EUDR Art. 9(1)(d), holdings ≤ 4 ha may use a single point; larger
holdings require a polygon with enough vertices to delineate the boundary.
Geometries are stored in EPSG:4326 (WGS 84) per the regulation's GeoJSON
guidance.
"""

from __future__ import annotations

import enum
import uuid

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eudr.models.base import Base
from eudr.models.organization import Organization


class Commodity(str, enum.Enum):
    COFFEE = "coffee"
    RUBBER = "rubber"
    WOOD = "wood"


class GeolocationType(str, enum.Enum):
    POINT = "point"
    POLYGON = "polygon"


class Plot(Base):
    __tablename__ = "plots"
    __table_args__ = (
        CheckConstraint("area_ha > 0", name="plots_area_positive"),
        CheckConstraint(
            "(geolocation_type = 'point' AND area_ha <= 4) OR geolocation_type = 'polygon'",
            name="plots_point_only_for_small_holdings",
        ),
        Index("plots_geom_gix", "geometry", postgresql_using="gist"),
    )

    producer_org_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    external_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    commodity: Mapped[Commodity] = mapped_column(
        Enum(Commodity, name="commodity"),
        nullable=False,
        index=True,
    )
    geolocation_type: Mapped[GeolocationType] = mapped_column(
        Enum(GeolocationType, name="geolocation_type"),
        nullable=False,
    )
    geometry: Mapped[object] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        nullable=False,
    )
    area_ha: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    planted_year: Mapped[int | None] = mapped_column(SmallInteger)
    ownership_proof_url: Mapped[str | None] = mapped_column(String(1024))
    cutoff_compliant: Mapped[bool | None] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(String(2048))

    producer: Mapped[Organization] = relationship(lazy="joined")
