"""Due Diligence Statement schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from eudr.models.dds import DDSStatus
from eudr.schemas.common import TimestampedID


class DDSCreate(BaseModel):
    lot_id: UUID
    operator_org_id: UUID
    mitigation_measures: str | None = Field(default=None, max_length=4096)


class DDSOut(TimestampedID):
    lot_id: UUID
    operator_org_id: UUID
    dds_reference: str
    status: DDSStatus
    traces_nt_reference: str | None
    traces_nt_verification_number: str | None
    submitted_at: datetime | None
    accepted_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    payload: dict
    risk_assessment: dict
    mitigation_measures: str | None


class DDSSubmitResponse(BaseModel):
    dds_id: UUID
    status: DDSStatus
    queued: bool
    detail: str
