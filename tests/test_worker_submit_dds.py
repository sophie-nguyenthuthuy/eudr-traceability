"""Tests for the async DDS-submission worker task.

We exercise the underlying ``_submit`` coroutine directly (not via Celery)
with the TRACES NT client monkeypatched, so we cover the full state
transition logic without spinning up a broker.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from eudr.errors import TracesNTError
from eudr.models import (
    Commodity,
    DDSStatus,
    DueDiligenceStatement,
    Harvest,
    Lot,
    LotComposition,
    LotStatus,
    Plot,
)
from eudr.services.traces_nt import TracesNTResponse


@pytest.fixture
def patch_worker_session(monkeypatch, engine):
    """The worker module imports ``SessionLocal`` from eudr.db, which is bound
    to a module-level engine created in whatever loop first imported it.
    Re-point it at the test engine (NullPool, current loop) for the duration
    of the test."""
    from eudr.workers import tasks

    test_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(tasks, "SessionLocal", test_factory)
    return test_factory


@pytest.fixture
async def pending_dds(session, admin_org):
    """A SEALED lot with a READY DDS, ready for submission."""
    plot = Plot(
        producer_org_id=admin_org.id,
        commodity=Commodity.COFFEE,
        geolocation_type="polygon",
        geometry=(
            "SRID=4326;POLYGON((108.05 12.66, 108.06 12.66, "
            "108.06 12.67, 108.05 12.67, 108.05 12.66))"
        ),
        area_ha=1.0,
        cutoff_compliant=True,
    )
    session.add(plot)
    await session.flush()

    harvest = Harvest(
        plot_id=plot.id,
        quantity_kg=1000,
        harvest_date=date(2025, 11, 1),
    )
    session.add(harvest)
    await session.flush()

    lot = Lot(
        lot_code="LOT-SUBMIT-001",
        commodity=Commodity.COFFEE,
        hs_code="0901",
        total_quantity_kg=1000,
        status=LotStatus.DDS_PENDING,
        current_holder_org_id=admin_org.id,
        compositions=[LotComposition(harvest_id=harvest.id, quantity_kg=1000)],
    )
    session.add(lot)
    await session.flush()

    dds = DueDiligenceStatement(
        lot_id=lot.id,
        operator_org_id=admin_org.id,
        dds_reference="EUDR-TEST-0001",
        status=DDSStatus.READY,
        payload={"lot": {"id": str(lot.id), "hs_code": "0901"}},
        risk_assessment={"classification": "negligible", "high_risk_plots": []},
    )
    session.add(dds)
    await session.commit()
    return dds


async def test_submit_happy_path_marks_dds_submitted(
    monkeypatch,
    patch_worker_session,
    pending_dds,
):
    """A successful TRACES NT submission flips the DDS to SUBMITTED and
    stores the reference + verification number returned by the EU."""

    class _FakeClient:
        async def submit(self, payload: dict) -> TracesNTResponse:
            assert payload["lot"]["hs_code"] == "0901"
            return TracesNTResponse(
                reference="TNT-REF-LIVE",
                verification_number="TNT-VER-LIVE",
                raw={"ok": True},
            )

    from eudr.workers import tasks

    monkeypatch.setattr(tasks, "TracesNTClient", lambda: _FakeClient())

    result = await tasks._submit(pending_dds.id)

    assert result == {"ok": True, "reference": "TNT-REF-LIVE"}

    # Re-fetch via the test factory (now binding the worker's SessionLocal too).
    async with patch_worker_session() as s:
        dds = (
            await s.execute(
                select(DueDiligenceStatement).where(
                    DueDiligenceStatement.id == pending_dds.id,
                ),
            )
        ).scalar_one()
        assert dds.status is DDSStatus.SUBMITTED
        assert dds.traces_nt_reference == "TNT-REF-LIVE"
        assert dds.traces_nt_verification_number == "TNT-VER-LIVE"
        assert dds.submitted_at is not None
        assert dds.submitted_at.tzinfo is not None
        # Lot tracked along
        lot = (await s.execute(select(Lot).where(Lot.id == dds.lot_id))).scalar_one()
        assert lot.status is LotStatus.DDS_SUBMITTED


async def test_submit_traces_nt_error_marks_rejected(
    monkeypatch,
    patch_worker_session,
    pending_dds,
):
    """A 4xx from TRACES NT (e.g. bad payload) marks the DDS REJECTED with
    a recorded reason and bubbles the exception so Celery retries kick in
    for the auto-retried (5xx) class only."""

    class _FailingClient:
        async def submit(self, payload: dict) -> TracesNTResponse:
            raise TracesNTError("DDS rejected: 422 missing geolocation")

    from eudr.workers import tasks

    monkeypatch.setattr(tasks, "TracesNTClient", lambda: _FailingClient())

    with pytest.raises(TracesNTError):
        await tasks._submit(pending_dds.id)

    async with patch_worker_session() as s:
        dds = (
            await s.execute(
                select(DueDiligenceStatement).where(
                    DueDiligenceStatement.id == pending_dds.id,
                ),
            )
        ).scalar_one()
        assert dds.status is DDSStatus.REJECTED
        assert dds.rejected_at is not None
        assert "missing geolocation" in (dds.rejection_reason or "")


async def test_submit_unknown_dds_returns_not_found(monkeypatch, patch_worker_session):
    """A submission task for a deleted DDS returns gracefully (no retry)."""

    from uuid import uuid4

    from eudr.workers import tasks

    # No client should be constructed; if it is, fail loudly.
    monkeypatch.setattr(
        tasks,
        "TracesNTClient",
        lambda: (_ for _ in ()).throw(AssertionError("client should not be built")),
    )

    result = await tasks._submit(uuid4())
    assert result == {"ok": False, "reason": "not_found"}
