from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eudr.models import (
    Commodity,
    Harvest,
    Lot,
    LotComposition,
    LotStatus,
    Organization,
    OrganizationType,
    Plot,
)
from eudr.models.custody import CustodyEventType
from eudr.services.chain_of_custody import record_event, verify_chain
from eudr.services.geo import geom_to_db, parse_geojson


@pytest.fixture
async def seeded_lot(session, admin_org, admin_user):
    cooperative = Organization(
        name="Coop", type=OrganizationType.COOPERATIVE, country_code="VN",
    )
    session.add(cooperative)
    await session.flush()

    plot = Plot(
        producer_org_id=cooperative.id,
        commodity=Commodity.COFFEE,
        geolocation_type="polygon",
        geometry=geom_to_db(parse_geojson({
            "type": "Polygon",
            "coordinates": [[
                [108.0500, 12.6667],
                [108.0510, 12.6667],
                [108.0510, 12.6677],
                [108.0500, 12.6677],
                [108.0500, 12.6667],
            ]],
        })),
        area_ha=1.2,
    )
    session.add(plot)
    await session.flush()

    harvest = Harvest(
        plot_id=plot.id,
        quantity_kg=500,
        harvest_date=datetime(2025, 11, 1, tzinfo=UTC).date(),
    )
    session.add(harvest)
    await session.flush()

    lot = Lot(
        lot_code="LOT-001",
        commodity=Commodity.COFFEE,
        hs_code="0901",
        total_quantity_kg=500,
        status=LotStatus.DRAFT,
        current_holder_org_id=cooperative.id,
        compositions=[LotComposition(harvest_id=harvest.id, quantity_kg=500)],
    )
    session.add(lot)
    await session.commit()
    return lot, cooperative, admin_user


async def test_chain_records_and_verifies(session, seeded_lot, admin_org) -> None:
    lot, cooperative, user = seeded_lot

    e1 = await record_event(
        session,
        lot_id=lot.id,
        event_type=CustodyEventType.TRANSFER,
        from_org_id=cooperative.id,
        to_org_id=admin_org.id,
        occurred_at=datetime.now(UTC),
        recorded_by_user_id=user.id,
        payload={"vehicle": "VN-12345"},
    )
    e2 = await record_event(
        session,
        lot_id=lot.id,
        event_type=CustodyEventType.TRANSFORMATION,
        occurred_at=datetime.now(UTC),
        recorded_by_user_id=user.id,
        payload={"process": "drying"},
    )
    await session.commit()

    assert e1.prev_hash is None
    assert e2.prev_hash == e1.event_hash

    ok, count = await verify_chain(session, lot.id)
    assert ok is True
    assert count == 2


async def test_chain_detects_tampering(session, seeded_lot, admin_org) -> None:
    lot, cooperative, user = seeded_lot
    await record_event(
        session,
        lot_id=lot.id,
        event_type=CustodyEventType.TRANSFER,
        from_org_id=cooperative.id,
        to_org_id=admin_org.id,
        occurred_at=datetime.now(UTC),
        recorded_by_user_id=user.id,
    )
    e2 = await record_event(
        session,
        lot_id=lot.id,
        event_type=CustodyEventType.TRANSFORMATION,
        occurred_at=datetime.now(UTC),
        recorded_by_user_id=user.id,
    )
    # Tamper.
    e2.payload = {"process": "altered"}
    await session.commit()

    ok, _ = await verify_chain(session, lot.id)
    assert ok is False
