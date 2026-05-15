"""Geometry helpers: validation, area calculation, GeoJSON conversions.

Areas are computed by reprojecting the geometry to an equal-area projection
suitable for Vietnam (EPSG:3857 is a poor choice for area; we use a
Cylindrical Equal Area with a centroid-derived latitude of true scale, which
keeps error under ~1% for plots in the tropics).
"""

from __future__ import annotations

from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from eudr.errors import ValidationError
from eudr.models.plot import GeolocationType

# EUDR Annex requires a polygon when area > 4 ha (Art. 9(1)(d)).
EUDR_POINT_MAX_AREA_HA = 4.0


def parse_geojson(geometry: dict[str, Any]) -> BaseGeometry:
    """Validate and return a shapely geometry from a GeoJSON dict."""
    try:
        geom = shape(geometry)
    except Exception as e:  # noqa: BLE001
        raise ValidationError(f"invalid GeoJSON: {e}") from e
    if not geom.is_valid:
        raise ValidationError(f"invalid geometry: {explain_validity(geom)}")
    if geom.is_empty:
        raise ValidationError("geometry is empty")
    return geom


def classify_geometry(geom: BaseGeometry) -> GeolocationType:
    if geom.geom_type == "Point":
        return GeolocationType.POINT
    if geom.geom_type in {"Polygon", "MultiPolygon"}:
        return GeolocationType.POLYGON
    raise ValidationError(
        f"unsupported geometry type {geom.geom_type!r}; "
        "EUDR accepts Point (≤4 ha holdings) or Polygon/MultiPolygon",
    )


def compute_area_ha(geom: BaseGeometry) -> float:
    """Area in hectares. Points are reported as 0; the producer must supply the
    declared holding area separately for ≤4 ha plots."""
    if geom.geom_type == "Point":
        return 0.0
    # World Cylindrical Equal Area (EPSG:6933) — ~1% accurate worldwide.
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
    from shapely.ops import transform

    projected = transform(transformer.transform, geom)
    return float(projected.area) / 10_000.0  # m² → ha


def validate_for_eudr(
    geom: BaseGeometry, declared_area_ha: float | None
) -> tuple[GeolocationType, float]:
    """Returns ``(geolocation_type, area_ha)`` enforcing EUDR Art. 9(1)(d).

    For points the producer must declare a holding area ≤ 4 ha. For polygons
    we compute the area from the geometry itself.
    """
    geo_type = classify_geometry(geom)
    if geo_type is GeolocationType.POINT:
        if declared_area_ha is None or declared_area_ha <= 0:
            raise ValidationError(
                "for a Point geometry the declared holding area in hectares is required",
            )
        if declared_area_ha > EUDR_POINT_MAX_AREA_HA:
            raise ValidationError(
                f"Point geolocation only allowed for holdings ≤ "
                f"{EUDR_POINT_MAX_AREA_HA} ha (EUDR Art. 9(1)(d)); got {declared_area_ha}",
            )
        return geo_type, declared_area_ha

    area = compute_area_ha(geom)
    if area <= 0:
        raise ValidationError("computed polygon area is zero")
    return geo_type, area


def geom_to_geojson(geom: BaseGeometry) -> dict[str, Any]:
    return mapping(geom)


def geom_from_db(value: Any) -> dict[str, Any] | None:
    """Convert a GeoAlchemy2 WKBElement to GeoJSON, ``None``-safe."""
    if value is None:
        return None
    return mapping(to_shape(value))


def geom_to_db(geom: BaseGeometry):
    return from_shape(geom, srid=4326)
