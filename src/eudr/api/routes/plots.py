"""Plot registry and deforestation checks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from eudr.deps import CurrentUserDep, PrincipalDep, SessionDep, require_role
from eudr.errors import ForbiddenError, NotFoundError
from eudr.models.deforestation import DeforestationCheck
from eudr.models.plot import Plot
from eudr.models.user import UserRole
from eudr.schemas.common import Page
from eudr.schemas.plot import DeforestationCheckOut, PlotCreate, PlotOut
from eudr.services.deforestation import check_plot_against_gfc, is_cutoff_compliant
from eudr.services.geo import (
    geom_from_db,
    geom_to_db,
    parse_geojson,
    validate_for_eudr,
)

router = APIRouter()


def _to_out(plot: Plot) -> PlotOut:
    return PlotOut.model_validate(
        {
            "id": plot.id,
            "created_at": plot.created_at,
            "updated_at": plot.updated_at,
            "producer_org_id": plot.producer_org_id,
            "external_ref": plot.external_ref,
            "commodity": plot.commodity,
            "geolocation_type": plot.geolocation_type,
            "geometry": geom_from_db(plot.geometry),
            "area_ha": float(plot.area_ha),
            "planted_year": plot.planted_year,
            "ownership_proof_url": plot.ownership_proof_url,
            "cutoff_compliant": plot.cutoff_compliant,
            "notes": plot.notes,
        },
    )


@router.get("", response_model=Page[PlotOut])
async def list_plots(
    session: SessionDep,
    _: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    producer_org_id: UUID | None = None,
) -> Page[PlotOut]:
    stmt = select(Plot)
    if producer_org_id is not None:
        stmt = stmt.where(Plot.producer_org_id == producer_org_id)
    total = (
        await session.execute(stmt.with_only_columns(func.count(Plot.id)))
    ).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(Plot.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    return Page(
        items=[_to_out(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=PlotOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_role(
                UserRole.PRODUCER,
                UserRole.COOPERATIVE_OFFICER,
                UserRole.ADMIN,
            ),
        ),
    ],
)
async def create_plot(
    session: SessionDep,
    user: CurrentUserDep,
    body: PlotCreate,
) -> PlotOut:
    if user.role is UserRole.PRODUCER and body.producer_org_id != user.organization_id:
        raise ForbiddenError("producers can only register plots for their own organization")

    geom = parse_geojson(body.geometry)
    geo_type, area_ha = validate_for_eudr(geom, body.declared_area_ha)

    plot = Plot(
        producer_org_id=body.producer_org_id,
        external_ref=body.external_ref,
        commodity=body.commodity,
        geolocation_type=geo_type,
        geometry=geom_to_db(geom),
        area_ha=area_ha,
        planted_year=body.planted_year,
        ownership_proof_url=body.ownership_proof_url,
        notes=body.notes,
    )
    session.add(plot)
    await session.flush()
    return _to_out(plot)


@router.get("/{plot_id}", response_model=PlotOut)
async def get_plot(plot_id: UUID, session: SessionDep, _: PrincipalDep) -> PlotOut:
    plot = (
        await session.execute(select(Plot).where(Plot.id == plot_id))
    ).scalar_one_or_none()
    if plot is None:
        raise NotFoundError(f"plot {plot_id} not found")
    return _to_out(plot)


@router.post(
    "/{plot_id}/deforestation-check",
    response_model=DeforestationCheckOut,
    status_code=status.HTTP_201_CREATED,
)
async def run_deforestation_check(
    plot_id: UUID,
    session: SessionDep,
    _: PrincipalDep,
) -> DeforestationCheckOut:
    plot = (
        await session.execute(select(Plot).where(Plot.id == plot_id))
    ).scalar_one_or_none()
    if plot is None:
        raise NotFoundError(f"plot {plot_id} not found")

    from shapely.geometry import shape

    geom_geojson: dict[str, Any] | None = geom_from_db(plot.geometry)
    if geom_geojson is None:
        raise NotFoundError(f"plot {plot_id} has no geometry stored")
    geom = shape(geom_geojson)
    result = await check_plot_against_gfc(geom)

    record = DeforestationCheck(
        plot_id=plot.id,
        source=result.source,
        cutoff_date=datetime(result.cutoff_year, 12, 31, tzinfo=UTC).date(),
        checked_at=result.checked_at,
        overlap_ha=result.overlap_ha,
        risk_score=result.risk_score,
        raw_result=result.raw,
    )
    session.add(record)
    plot.cutoff_compliant = is_cutoff_compliant(result)
    await session.flush()

    return DeforestationCheckOut.model_validate(
        {
            "id": record.id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "plot_id": record.plot_id,
            "source": record.source.value,
            "cutoff_date": record.cutoff_date,
            "overlap_ha": float(record.overlap_ha),
            "risk_score": float(record.risk_score),
            "notes": record.notes,
        },
    )
