"""Shared pytest fixtures.

DB strategy: a single Postgres+PostGIS instance (the one CI provides under
``DATABASE_URL`` or a testcontainers-spawned one locally). Each test runs in
its own transaction that is rolled back, so tests stay isolated without
re-running migrations per case.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from eudr.db import get_session
from eudr.main import create_app
from eudr.models import Base, Organization, OrganizationType, User, UserRole
from eudr.security import hash_password, issue_access_token


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://eudr:eudr@localhost:5432/eudr_test",
    )


@pytest_asyncio.fixture(scope="session")
async def engine(database_url: str):
    # NullPool: each test connection is opened fresh in the current event loop
    # and closed after use. This avoids the classic asyncpg + pytest-asyncio
    # "Future attached to a different loop" error caused by the session-scoped
    # engine pooling connections opened in one loop and lent to tests running
    # in a different loop.
    eng = create_async_engine(database_url, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    sess_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sess_factory() as session:
        try:
            yield session
        finally:
            # Wipe data between tests; cheaper than rolling back nested savepoints
            # given the small table count in this service.
            for tbl in reversed(Base.metadata.sorted_tables):
                await session.execute(tbl.delete())
            await session.commit()


@pytest_asyncio.fixture
async def app(session: AsyncSession):
    app = create_app()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    return app


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_org(session: AsyncSession) -> Organization:
    org = Organization(
        name="EUDR Admin Co.",
        type=OrganizationType.EXPORTER,
        country_code="VN",
    )
    session.add(org)
    await session.commit()
    return org


@pytest_asyncio.fixture
async def admin_user(session: AsyncSession, admin_org: Organization) -> User:
    user = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("correct-horse-battery-staple"),
        full_name="Admin",
        organization_id=admin_org.id,
        role=UserRole.ADMIN,
    )
    session.add(user)
    await session.commit()
    return user


@pytest.fixture
def auth_header(admin_user: User) -> dict[str, str]:
    token, _ = issue_access_token(
        user_id=admin_user.id,
        organization_id=admin_user.organization_id,
        role=admin_user.role.value,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)
