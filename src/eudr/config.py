"""Application settings loaded from environment variables.

We use pydantic-settings so every config value is typed, validated at startup,
and easy to override in tests.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    secret_key: str = Field(min_length=16)

    # ---- DB ----
    database_url: str  # async, asyncpg driver
    database_url_sync: str  # sync, used by alembic
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ---- Auth ----
    jwt_private_key_path: Path = Path("/run/secrets/jwt-private.pem")
    jwt_public_key_path: Path = Path("/run/secrets/jwt-public.pem")
    jwt_issuer: str = "eudr-traceability"
    jwt_access_ttl_seconds: int = 3600
    jwt_refresh_ttl_seconds: int = 2_592_000

    # ---- Redis / Celery ----
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ---- MinIO (S3-compatible object storage) ----
    minio_endpoint: str | None = None
    minio_region: str = "us-east-1"
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket_documents: str = "eudr-documents"
    minio_bucket_dds: str = "eudr-dds-payloads"
    minio_bucket_rasters: str = "eudr-rasters"

    # ---- EU TRACES NT ----
    traces_nt_env: Literal["sandbox", "production"] = "sandbox"
    traces_nt_base_url: str = "https://webgate.training.ec.europa.eu/tracesnt-api"
    traces_nt_client_id: str | None = None
    traces_nt_client_secret: str | None = None

    # ---- Deforestation data ----
    hansen_gfc_raster_url: str | None = None
    jrc_tmf_raster_url: str | None = None
    eudr_cutoff_date: date = date(2020, 12, 31)

    # ---- Observability ----
    otel_exporter_otlp_endpoint: str | None = None
    prometheus_metrics_enabled: bool = True

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def jwt_private_key(self) -> str:
        return self.jwt_private_key_path.read_text()

    @property
    def jwt_public_key(self) -> str:
        return self.jwt_public_key_path.read_text()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
