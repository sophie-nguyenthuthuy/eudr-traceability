"""Plot schemas."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from eudr.models.plot import Commodity, GeolocationType
from eudr.schemas.common import GeoJSONGeometry, TimestampedID


class PlotCreate(BaseModel):
    producer_org_id: UUID
    external_ref: str | None = Field(default=None, max_length=128)
    commodity: Commodity
    geometry: GeoJSONGeometry
    planted_year: int | None = Field(default=None, ge=1900, le=2100)
    ownership_proof_url: str | None = Field(default=None, max_length=1024)
    notes: str | None = Field(default=None, max_length=2048)


class PlotOut(TimestampedID):
    producer_org_id: UUID
    external_ref: str | None
    commodity: Commodity
    geolocation_type: GeolocationType
    geometry: GeoJSONGeometry
    area_ha: float
    planted_year: int | None
    ownership_proof_url: str | None
    cutoff_compliant: bool | None
    notes: str | None


class DeforestationCheckOut(TimestampedID):
    plot_id: UUID
    source: str
    cutoff_date: date
    overlap_ha: float
    risk_score: float
    notes: str | None
