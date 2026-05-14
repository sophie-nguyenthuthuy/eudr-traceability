"""Organization schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from eudr.models.organization import OrganizationType
from eudr.schemas.common import TimestampedID


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: OrganizationType
    country_code: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    address: str | None = Field(default=None, max_length=1024)
    tax_id: str | None = Field(default=None, max_length=64)
    eori_number: str | None = Field(default=None, max_length=64)


class OrganizationOut(TimestampedID):
    name: str
    type: OrganizationType
    country_code: str
    address: str | None
    tax_id: str | None
    eori_number: str | None
