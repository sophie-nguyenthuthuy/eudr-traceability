"""Celery tasks: DDS submission, periodic plot rechecks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from eudr.db import SessionLocal
from eudr.errors import TracesNTError
from eudr.logging_config import configure_logging, get_logger
from eudr.models.dds import DDSStatus, DueDiligenceStatement
from eudr.models.lot import LotStatus
from eudr.models.plot import Plot
from eudr.services.traces_nt import TracesNTClient
from eudr.workers.celery_app import celery_app

configure_logging()
log = get_logger(__name__)


def _run(coro):
    """Run an async coroutine from a sync Celery worker."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _submit(dds_id: UUID) -> dict[str, Any]:
    async with SessionLocal() as session:
        dds = (
            await session.execute(
                select(DueDiligenceStatement).where(DueDiligenceStatement.id == dds_id),
            )
        ).scalar_one_or_none()
        if dds is None:
            log.warning("dds.submit.not_found", dds_id=str(dds_id))
            return {"ok": False, "reason": "not_found"}

        try:
            client = TracesNTClient()
            resp = await client.submit(dds.payload)
        except TracesNTError as e:
            dds.status = DDSStatus.REJECTED
            dds.rejected_at = datetime.now(UTC)
            dds.rejection_reason = str(e)
            await session.commit()
            log.error("dds.submit.failed", dds_id=str(dds_id), error=str(e))
            raise

        dds.status = DDSStatus.SUBMITTED
        dds.submitted_at = datetime.now(UTC)
        dds.traces_nt_reference = resp.reference
        dds.traces_nt_verification_number = resp.verification_number
        dds.lot.status = LotStatus.DDS_SUBMITTED
        await session.commit()
        log.info(
            "dds.submit.ok",
            dds_id=str(dds_id),
            reference=resp.reference,
        )
        return {"ok": True, "reference": resp.reference}


@celery_app.task(
    bind=True,
    name="eudr.workers.tasks.submit_dds_task",
    autoretry_for=(TracesNTError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=6,
)
def submit_dds_task(self, dds_id: str) -> dict[str, Any]:  # noqa: ARG001
    return _run(_submit(UUID(dds_id)))


async def _recheck_all() -> int:
    """Re-run the deforestation check for every plot. Cheap when stubbed,
    cheap-ish with cloud-optimized GeoTIFFs and windowed reads in prod."""
    from shapely.geometry import shape

    from eudr.models.deforestation import DeforestationCheck
    from eudr.services.deforestation import check_plot_against_gfc, is_cutoff_compliant
    from eudr.services.geo import geom_from_db

    async with SessionLocal() as session:
        plots = list((await session.execute(select(Plot))).scalars())
        for plot in plots:
            geom_dict = geom_from_db(plot.geometry)
            if not geom_dict:
                continue
            result = await check_plot_against_gfc(shape(geom_dict))
            session.add(
                DeforestationCheck(
                    plot_id=plot.id,
                    source=result.source,
                    cutoff_date=datetime(result.cutoff_year, 12, 31, tzinfo=UTC).date(),
                    checked_at=result.checked_at,
                    overlap_ha=result.overlap_ha,
                    risk_score=result.risk_score,
                    raw_result=result.raw,
                ),
            )
            plot.cutoff_compliant = is_cutoff_compliant(result)
        await session.commit()
        return len(plots)


@celery_app.task(name="eudr.workers.tasks.recheck_all_plots")
def recheck_all_plots() -> int:
    return _run(_recheck_all())
