"""Declarative base and shared column mixins."""

from __future__ import annotations

import enum as py_enum
import uuid
from datetime import datetime
from typing import Annotated, TypeVar

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

E = TypeVar("E", bound=py_enum.Enum)


def pg_enum(py_cls: type[E], name: str) -> Enum:
    """SQLAlchemy Enum that serializes the *value*, not the *name*.

    Python convention: ``OrganizationType.COOPERATIVE`` has name='COOPERATIVE'
    and value='cooperative'. By default SQLAlchemy stores the name, but our
    Postgres enum types use the lowercase values — so we always need to pass
    a values_callable. Centralise that here.
    """
    return Enum(
        py_cls,
        name=name,
        values_callable=lambda cls: [m.value for m in cls],
    )

UUIDPK = Annotated[
    uuid.UUID,
    mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
]
TimestampCreate = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
]
TimestampUpdate = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
]


class Base(DeclarativeBase):
    """Common base. Every table gets a UUID PK and created/updated timestamps."""

    id: Mapped[UUIDPK]
    created_at: Mapped[TimestampCreate]
    updated_at: Mapped[TimestampUpdate]
