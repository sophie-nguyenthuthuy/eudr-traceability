"""Harvest schemas."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from eudr.schemas.common import TimestampedID


class HarvestCreate(BaseModel):
    plot_id: UUID
    quantity_kg: float = Field(gt=0)
    harvest_date: date
    external_ref: str | None = Field(default=None, max_length=128)


class HarvestOut(TimestampedID):
    plot_id: UUID
    quantity_kg: float
    harvest_date: date
    external_ref: str | None
