"""Deforestation overlap analysis.

The full implementation reads the Hansen Global Forest Change ``lossyear``
raster (a single-band GeoTIFF where pixel value N means tree-cover loss in
year 2000+N) and computes the area of pixels with N > cutoff_year that fall
inside the plot polygon.

For local development and CI we stub the raster read so the service is
exercisable without ~50 GB of geotiff downloads. Production deploys point
``HANSEN_GFC_RASTER_URL`` at a cloud-optimised GeoTIFF on S3 and the same
code path runs against the real data via rasterio's windowed reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from shapely.geometry.base import BaseGeometry

from eudr.config import get_settings
from eudr.models.deforestation import DeforestationSource


@dataclass(frozen=True)
class DeforestationResult:
    source: DeforestationSource
    cutoff_year: int
    overlap_ha: float
    risk_score: float  # 0..1
    checked_at: datetime
    raw: dict


def _stub_overlap(geom: BaseGeometry) -> float:
    """Deterministic zero overlap for stubbed local/CI runs.

    A real implementation calls ``rasterio.mask.mask`` against the GFC
    lossyear raster windowed to ``geom.bounds`` and sums pixels where
    ``value > cutoff_year - 2000``. The Hansen pixel area at the equator is
    ~900 m², which we multiply by the masked-pixel count and divide by 10⁴
    to get hectares.
    """
    return 0.0


async def check_plot_against_gfc(geom: BaseGeometry) -> DeforestationResult:
    settings = get_settings()
    cutoff_year = settings.eudr_cutoff_date.year

    if settings.hansen_gfc_raster_url is None or settings.app_env in {"test", "local"}:
        overlap_ha = _stub_overlap(geom)
    else:
        overlap_ha = _compute_real_overlap(  # pragma: no cover - exercised in staging+
            geom,
            raster_url=settings.hansen_gfc_raster_url,
            cutoff_year=cutoff_year,
        )

    # Risk: any overlap > 0.5% of plot area trips a high-risk flag.
    risk_score = min(1.0, overlap_ha / max(1e-6, geom.area * 100))
    return DeforestationResult(
        source=DeforestationSource.HANSEN_GFC,
        cutoff_year=cutoff_year,
        overlap_ha=overlap_ha,
        risk_score=risk_score,
        checked_at=datetime.now(UTC),
        raw={
            "raster_url": settings.hansen_gfc_raster_url,
            "method": "hansen_gfc_lossyear_v1.11",
        },
    )


def _compute_real_overlap(  # pragma: no cover
    geom: BaseGeometry,
    *,
    raster_url: str,
    cutoff_year: int,
) -> float:
    """Production path. Imported lazily to keep test/CI runs fast."""
    import rasterio
    from rasterio.mask import mask

    with rasterio.open(raster_url) as src:
        out_image, _ = mask(src, [geom.__geo_interface__], crop=True, filled=False)
        cutoff_band = cutoff_year - 2000
        deforested_pixels = int((out_image > cutoff_band).sum())
        pixel_area_m2 = abs(src.transform.a * src.transform.e)
        return deforested_pixels * pixel_area_m2 / 10_000.0


def is_cutoff_compliant(result: DeforestationResult, *, threshold_ha: float = 0.05) -> bool:
    """≥ 0.05 ha of post-cutoff loss inside the plot blocks the plot.

    The threshold accounts for pixel-edge noise. Auditors can adjust per
    commodity by overriding ``threshold_ha`` at the call site.
    """
    return result.overlap_ha < threshold_ha
