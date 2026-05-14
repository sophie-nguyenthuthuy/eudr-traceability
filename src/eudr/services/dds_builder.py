"""Assemble the EU TRACES NT Due Diligence Statement payload for a lot.

The structure mirrors the TRACES NT DDS JSON schema. The integration is
versioned via ``DDS_SCHEMA_VERSION`` so we can recompile payloads when the
Commission revises the schema.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from eudr.errors import ConflictError, NotFoundError
from eudr.models.custody import CustodyEvent
from eudr.models.deforestation import DeforestationCheck
from eudr.models.dds import DDSStatus, DueDiligenceStatement
from eudr.models.lot import Lot, LotStatus
from eudr.models.organization import Organization
from eudr.models.plot import Plot
from eudr.services.geo import geom_from_db

DDS_SCHEMA_VERSION = "1.4"  # TRACES NT DDS schema we target


def _generate_reference() -> str:
    return f"EUDR-{datetime.now(UTC):%Y%m%d}-{secrets.token_hex(6).upper()}"


async def _load_lot(session: AsyncSession, lot_id: UUID) -> Lot:
    stmt = (
        select(Lot)
        .options(selectinload(Lot.compositions))
        .where(Lot.id == lot_id)
    )
    lot = (await session.execute(stmt)).scalar_one_or_none()
    if lot is None:
        raise NotFoundError(f"lot {lot_id} not found")
    return lot


async def _plots_for_lot(session: AsyncSession, lot: Lot) -> list[Plot]:
    plot_ids = [c.harvest.plot_id for c in lot.compositions]
    stmt = select(Plot).where(Plot.id.in_(plot_ids))
    return list((await session.execute(stmt)).scalars())


async def _latest_check(session: AsyncSession, plot_id: UUID) -> DeforestationCheck | None:
    stmt = (
        select(DeforestationCheck)
        .where(DeforestationCheck.plot_id == plot_id)
        .order_by(DeforestationCheck.checked_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def build_payload(session: AsyncSession, lot_id: UUID, operator: Organization) -> dict[str, Any]:
    lot = await _load_lot(session, lot_id)
    plots = await _plots_for_lot(session, lot)

    if not plots:
        raise ConflictError(f"lot {lot_id} has no plots in its composition")

    producers: dict[UUID, dict[str, Any]] = {}
    geolocations: list[dict[str, Any]] = []
    for plot in plots:
        check = await _latest_check(session, plot.id)
        if plot.cutoff_compliant is False:
            raise ConflictError(
                f"plot {plot.id} failed the cutoff deforestation check; cannot build DDS",
            )
        producers.setdefault(
            plot.producer_org_id,
            {"organization_id": str(plot.producer_org_id)},
        )
        geolocations.append(
            {
                "plot_id": str(plot.id),
                "producer_organization_id": str(plot.producer_org_id),
                "commodity": plot.commodity.value,
                "geolocation_type": plot.geolocation_type.value,
                "geometry": geom_from_db(plot.geometry),
                "area_ha": float(plot.area_ha),
                "planted_year": plot.planted_year,
                "deforestation_check": (
                    {
                        "source": check.source.value,
                        "cutoff_date": check.cutoff_date.isoformat(),
                        "overlap_ha": float(check.overlap_ha),
                        "risk_score": float(check.risk_score),
                        "checked_at": check.checked_at.isoformat(),
                    }
                    if check is not None
                    else None
                ),
            },
        )

    custody_stmt = (
        select(CustodyEvent)
        .where(CustodyEvent.lot_id == lot.id)
        .order_by(CustodyEvent.occurred_at.asc())
    )
    custody_events = list((await session.execute(custody_stmt)).scalars())

    payload = {
        "schema_version": DDS_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "operator": {
            "organization_id": str(operator.id),
            "name": operator.name,
            "country_code": operator.country_code,
            "eori_number": operator.eori_number,
            "tax_id": operator.tax_id,
        },
        "lot": {
            "id": str(lot.id),
            "lot_code": lot.lot_code,
            "commodity": lot.commodity.value,
            "hs_code": lot.hs_code,
            "total_quantity_kg": float(lot.total_quantity_kg),
        },
        "producers": list(producers.values()),
        "geolocations": geolocations,
        "chain_of_custody": [
            {
                "event_id": str(e.id),
                "event_type": e.event_type.value,
                "from_org_id": str(e.from_org_id) if e.from_org_id else None,
                "to_org_id": str(e.to_org_id) if e.to_org_id else None,
                "occurred_at": e.occurred_at.isoformat(),
                "event_hash": e.event_hash,
                "prev_hash": e.prev_hash,
                "document_url": e.document_url,
            }
            for e in custody_events
        ],
    }
    return payload


def build_risk_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    """Negligible-risk classification per Art. 10 of EUDR.

    A lot is classified ``negligible`` when:
      - every plot has a recent deforestation check with risk_score < 0.01, and
      - every plot's cutoff_compliant flag is True.
    Otherwise the operator must record mitigation measures (Art. 11).
    """
    high_risk_plots: list[str] = []
    for geo in payload.get("geolocations", []):
        check = geo.get("deforestation_check")
        if check is None or check.get("risk_score", 1.0) >= 0.01:
            high_risk_plots.append(geo["plot_id"])
    return {
        "framework": "EUDR Art. 10/11",
        "high_risk_plots": high_risk_plots,
        "classification": "negligible" if not high_risk_plots else "non_negligible",
    }


async def create_dds(
    session: AsyncSession,
    *,
    lot_id: UUID,
    operator_org_id: UUID,
    mitigation_measures: str | None,
) -> DueDiligenceStatement:
    operator = (
        await session.execute(select(Organization).where(Organization.id == operator_org_id))
    ).scalar_one_or_none()
    if operator is None:
        raise NotFoundError(f"operator org {operator_org_id} not found")

    payload = await build_payload(session, lot_id, operator)
    risk = build_risk_assessment(payload)

    if risk["classification"] != "negligible" and not mitigation_measures:
        raise ConflictError(
            "non-negligible risk requires mitigation measures (EUDR Art. 11)",
        )

    lot = await _load_lot(session, lot_id)
    dds = DueDiligenceStatement(
        lot_id=lot_id,
        operator_org_id=operator_org_id,
        dds_reference=_generate_reference(),
        status=DDSStatus.READY,
        payload=payload,
        risk_assessment=risk,
        mitigation_measures=mitigation_measures,
    )
    lot.status = LotStatus.DDS_PENDING
    session.add(dds)
    await session.flush()
    return dds
