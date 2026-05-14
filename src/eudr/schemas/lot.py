"""Lot schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from eudr.models.lot import LotStatus
from eudr.models.plot import Commodity
from eudr.schemas.common import TimestampedID

# HS codes covered by this service: 0901 coffee, 4001 natural rubber, 4401-4421 wood.
HS_CODE_REGEX = r"^(0901|4001|44\d{2})(\.\d{2,4})?$"


class LotCompositionInput(BaseModel):
    harvest_id: UUID
    quantity_kg: float = Field(gt=0)


class LotCreate(BaseModel):
    lot_code: str = Field(min_length=1, max_length=64)
    commodity: Commodity
    hs_code: str = Field(pattern=HS_CODE_REGEX)
    compositions: list[LotCompositionInput] = Field(min_length=1)
    current_holder_org_id: UUID


class LotCompositionOut(TimestampedID):
    harvest_id: UUID
    quantity_kg: float


class LotOut(TimestampedID):
    lot_code: str
    commodity: Commodity
    hs_code: str
    total_quantity_kg: float
    status: LotStatus
    current_holder_org_id: UUID
    compositions: list[LotCompositionOut]
