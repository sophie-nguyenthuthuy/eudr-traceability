"""Organizations: producers, cooperatives, processors, exporters, auditors."""

from __future__ import annotations

import enum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from eudr.models.base import Base, pg_enum


class OrganizationType(str, enum.Enum):
    PRODUCER = "producer"
    COOPERATIVE = "cooperative"
    PROCESSOR = "processor"
    EXPORTER = "exporter"
    AUDITOR = "auditor"


class Organization(Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[OrganizationType] = mapped_column(
        pg_enum(OrganizationType, "organization_type"),
        nullable=False,
        index=True,
    )
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    address: Mapped[str | None] = mapped_column(String(1024))
    tax_id: Mapped[str | None] = mapped_column(String(64), index=True)
    eori_number: Mapped[str | None] = mapped_column(String(64), index=True)
