"""Top-level API router. Versioned under ``/api/v1``."""

from __future__ import annotations

from fastapi import APIRouter

from eudr.api.routes import (
    auth,
    custody,
    dds,
    harvests,
    health,
    lots,
    organizations,
    plots,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth.router, prefix="/auth", tags=["auth"])
v1.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
v1.include_router(plots.router, prefix="/plots", tags=["plots"])
v1.include_router(harvests.router, prefix="/harvests", tags=["harvests"])
v1.include_router(lots.router, prefix="/lots", tags=["lots"])
v1.include_router(custody.router, prefix="/custody", tags=["custody"])
v1.include_router(dds.router, prefix="/dds", tags=["dds"])
api_router.include_router(v1)
