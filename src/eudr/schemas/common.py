"""Shared request/response building blocks."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for response models populated from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class TimestampedID(ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


# GeoJSON: keep it loose – we validate properly in services/geo.py with shapely.
GeoJSONGeometry = Annotated[
    dict[str, Any],
    Field(
        description=(
            "GeoJSON geometry in WGS 84 (EPSG:4326). Must be a Point for plots "
            "of 4 ha or less, otherwise a Polygon or MultiPolygon."
        ),
        examples=[
            {"type": "Point", "coordinates": [108.0500, 12.6667]},
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [108.0500, 12.6667],
                        [108.0510, 12.6667],
                        [108.0510, 12.6677],
                        [108.0500, 12.6677],
                        [108.0500, 12.6667],
                    ],
                ],
            },
        ],
    ),
]
