"""Unit tests for the geo service — no DB required."""

from __future__ import annotations

import pytest

from eudr.errors import ValidationError
from eudr.models.plot import GeolocationType
from eudr.services.geo import (
    classify_geometry,
    compute_area_ha,
    parse_geojson,
    validate_for_eudr,
)


def test_parse_polygon_ok() -> None:
    geom = parse_geojson(
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
    )
    assert classify_geometry(geom) is GeolocationType.POLYGON
    assert compute_area_ha(geom) > 0


def test_parse_point_ok() -> None:
    geom = parse_geojson({"type": "Point", "coordinates": [108.05, 12.66]})
    assert classify_geometry(geom) is GeolocationType.POINT
    assert compute_area_ha(geom) == 0.0


def test_invalid_type_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_geojson({"type": "LineString", "coordinates": [[0, 0], [1, 1]]})


def test_point_requires_declared_area() -> None:
    geom = parse_geojson({"type": "Point", "coordinates": [108.05, 12.66]})
    with pytest.raises(ValidationError):
        validate_for_eudr(geom, declared_area_ha=None)


def test_point_rejected_when_area_over_4ha() -> None:
    geom = parse_geojson({"type": "Point", "coordinates": [108.05, 12.66]})
    with pytest.raises(ValidationError):
        validate_for_eudr(geom, declared_area_ha=4.5)


def test_point_accepted_under_4ha() -> None:
    geom = parse_geojson({"type": "Point", "coordinates": [108.05, 12.66]})
    geo_type, area = validate_for_eudr(geom, declared_area_ha=2.5)
    assert geo_type is GeolocationType.POINT
    assert area == 2.5
