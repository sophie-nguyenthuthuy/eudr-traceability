from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from eudr.errors import ConflictError
from eudr.models import (
    Commodity,
    DeforestationCheck,
    DeforestationSource,
    Harvest,
    Lot,
    LotComposition,
    LotStatus,
    Organization,
    OrganizationType,
    Plot,
)
from eudr.services.dds_builder import build_risk_assessment, create_dds
from eudr.services.geo import geom_to_db, parse_geojson


@pytest.fixture
async def lot_ready_for_dds(session, admin_org):
    producer = Organization(name="P", type=OrganizationType.PRODUCER, country_code="VN")
    session.add(producer)
    await session.flush()

    plot = Plot(
        producer_org_id=producer.id,
        commodity=Commodity.COFFEE,
        geolocation_type="polygon",
        geometry=geom_to_db(
            parse_geojson(
                {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [108.0500, 12.6667],
                            [108.0510, 12.6667],
                            [108.0510, 12.6677],
                            [108.0500, 12.6677],
                            [108.0500, 12.6667],
                        ]
                    ],
                }
            )
        ),
        area_ha=1.0,
        cutoff_compliant=True,
    )
    session.add(plot)
    await session.flush()

    session.add(
        DeforestationCheck(
            plot_id=plot.id,
            source=DeforestationSource.HANSEN_GFC,
            cutoff_date=date(2020, 12, 31),
            checked_at=datetime.now(UTC),
            overlap_ha=0,
            risk_score=0,
        ),
    )

    harvest = Harvest(
        plot_id=plot.id,
        quantity_kg=1000,
        harvest_date=datetime(2025, 11, 1, tzinfo=UTC).date(),
    )
    session.add(harvest)
    await session.flush()

    lot = Lot(
        lot_code="LOT-EXP-001",
        commodity=Commodity.COFFEE,
        hs_code="0901",
        total_quantity_kg=1000,
        status=LotStatus.SEALED,
        current_holder_org_id=admin_org.id,
        compositions=[LotComposition(harvest_id=harvest.id, quantity_kg=1000)],
    )
    session.add(lot)
    await session.commit()
    return lot


async def test_build_dds_negligible(session, lot_ready_for_dds, admin_org) -> None:
    dds = await create_dds(
        session,
        lot_id=lot_ready_for_dds.id,
        operator_org_id=admin_org.id,
        mitigation_measures=None,
    )
    await session.commit()
    assert dds.dds_reference.startswith("EUDR-")
    assert dds.risk_assessment["classification"] == "negligible"
    assert dds.payload["lot"]["hs_code"] == "0901"
    assert len(dds.payload["geolocations"]) == 1


async def test_non_negligible_requires_mitigation(session, lot_ready_for_dds, admin_org) -> None:
    # build_risk_assessment is pure — exercise its classification logic first.
    payload = {
        "geolocations": [
            {
                "plot_id": "x",
                "deforestation_check": {"risk_score": 0.5},
            },
        ],
    }
    assessment = build_risk_assessment(payload)
    assert assessment["classification"] == "non_negligible"

    # And the create_dds path rejects when the lot's plot is non-compliant.
    # Avoid lazy-loading the lot → composition → harvest → plot chain (which
    # would trigger async I/O outside a greenlet); fetch the plot directly.
    from sqlalchemy import select

    from eudr.models import Plot

    plot = (await session.execute(select(Plot))).scalars().first()
    assert plot is not None
    plot.cutoff_compliant = False
    await session.commit()

    with pytest.raises(ConflictError):
        await create_dds(
            session,
            lot_id=lot_ready_for_dds.id,
            operator_org_id=admin_org.id,
            mitigation_measures=None,
        )
