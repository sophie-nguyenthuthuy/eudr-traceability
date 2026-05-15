"""Seed a demo dataset: an admin user, a Đắk Lắk coffee cooperative, three
plots, harvests, a sealed lot, custody events, and a draft DDS.

Run with: ``docker compose run --rm api python -m scripts.seed_demo``
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import select

from eudr.db import SessionLocal
from eudr.logging_config import configure_logging, get_logger
from eudr.models import (
    Commodity,
    Harvest,
    Lot,
    LotComposition,
    LotStatus,
    Organization,
    OrganizationType,
    Plot,
    User,
    UserRole,
)
from eudr.models.custody import CustodyEventType
from eudr.security import hash_password
from eudr.services.chain_of_custody import record_event
from eudr.services.geo import geom_to_db, parse_geojson

log = get_logger(__name__)

# Three small coffee plots near Buôn Ma Thuột, Đắk Lắk.
DEMO_PLOTS = [
    {
        "external_ref": "DLK-001",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [108.0420, 12.6800],
                    [108.0440, 12.6800],
                    [108.0440, 12.6820],
                    [108.0420, 12.6820],
                    [108.0420, 12.6800],
                ],
            ],
        },
        "planted_year": 2012,
    },
    {
        "external_ref": "DLK-002",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [108.0500, 12.6850],
                    [108.0520, 12.6850],
                    [108.0520, 12.6870],
                    [108.0500, 12.6870],
                    [108.0500, 12.6850],
                ],
            ],
        },
        "planted_year": 2015,
    },
    {
        "external_ref": "DLK-003",
        "geometry": {"type": "Point", "coordinates": [108.0600, 12.6900]},
        "planted_year": 2018,
        "declared_area_ha": 2.0,
    },
]


async def _seed() -> None:
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(User).where(User.email == "admin@eudr.example.com"))
        ).scalar_one_or_none()
        if existing:
            log.info("seed.skip", reason="already_seeded")
            return

        coop = Organization(
            name="HTX Cà Phê Đắk Lắk",
            type=OrganizationType.COOPERATIVE,
            country_code="VN",
            address="Buôn Ma Thuột, Đắk Lắk",
            tax_id="0301234567",
        )
        exporter = Organization(
            name="VN Coffee Exporters JSC",
            type=OrganizationType.EXPORTER,
            country_code="VN",
            address="District 1, Ho Chi Minh City",
            tax_id="0309876543",
            eori_number="VN123456789012",
        )
        session.add_all([coop, exporter])
        await session.flush()

        admin = User(
            email="admin@eudr.example.com",
            password_hash=hash_password("changeme1234"),
            full_name="Demo Admin",
            organization_id=exporter.id,
            role=UserRole.ADMIN,
        )
        session.add(admin)
        await session.flush()

        plots: list[Plot] = []
        for spec in DEMO_PLOTS:
            geom = parse_geojson(spec["geometry"])
            from eudr.services.geo import validate_for_eudr

            geo_type, area_ha = validate_for_eudr(geom, spec.get("declared_area_ha"))
            plot = Plot(
                producer_org_id=coop.id,
                external_ref=spec["external_ref"],
                commodity=Commodity.COFFEE,
                geolocation_type=geo_type,
                geometry=geom_to_db(geom),
                area_ha=area_ha,
                planted_year=spec["planted_year"],
                cutoff_compliant=True,
            )
            plots.append(plot)
            session.add(plot)
        await session.flush()

        harvests: list[Harvest] = []
        for plot in plots:
            h = Harvest(
                plot_id=plot.id,
                quantity_kg=2500,
                harvest_date=date(2025, 11, 15),
            )
            harvests.append(h)
            session.add(h)
        await session.flush()

        lot = Lot(
            lot_code="LOT-COFFEE-2025-001",
            commodity=Commodity.COFFEE,
            hs_code="0901.21",
            total_quantity_kg=2500 * len(harvests),
            status=LotStatus.SEALED,
            current_holder_org_id=exporter.id,
            compositions=[
                LotComposition(harvest_id=h.id, quantity_kg=2500) for h in harvests
            ],
        )
        session.add(lot)
        await session.flush()

        await record_event(
            session,
            lot_id=lot.id,
            event_type=CustodyEventType.TRANSFER,
            from_org_id=coop.id,
            to_org_id=exporter.id,
            occurred_at=datetime.now(UTC),
            recorded_by_user_id=admin.id,
            payload={"transport": "truck", "license_plate": "47C-12345"},
        )
        await session.commit()
        log.info(
            "seed.ok",
            cooperative_id=str(coop.id),
            exporter_id=str(exporter.id),
            lot_id=str(lot.id),
            login="admin@eudr.example.com / changeme1234",
        )


def main() -> None:
    configure_logging()
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
