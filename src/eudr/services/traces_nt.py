"""Client for the EU TRACES NT DDS submission endpoint.

The live endpoints and exact request envelope are governed by EU Commission
technical specifications. We isolate that surface here so an updated spec or
a swap to the production endpoint is a config-only change.

Authentication is OAuth2 client credentials. The access token is cached in
Redis (via the worker) and refreshed when it expires. For tests, callers
inject a ``transport`` so no real HTTP is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from eudr.config import get_settings
from eudr.errors import TracesNTError
from eudr.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class TracesNTResponse:
    reference: str
    verification_number: str | None
    raw: dict[str, Any]


class TracesNTClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = get_settings()
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.traces_nt_base_url,
            timeout=30.0,
            transport=self._transport,
            headers={"User-Agent": "eudr-traceability/0.1"},
        )

    async def _token(self) -> str:
        if not self.settings.traces_nt_client_id or not self.settings.traces_nt_client_secret:
            raise TracesNTError("TRACES NT credentials not configured")
        async with self._client() as client:
            resp = await client.post(
                "/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.traces_nt_client_id,
                    "client_secret": self.settings.traces_nt_client_secret,
                    "scope": "dds.submit",
                },
            )
            if resp.status_code != 200:
                raise TracesNTError(
                    f"token endpoint returned {resp.status_code}: {resp.text[:200]}",
                )
            return str(resp.json()["access_token"])

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, TracesNTError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def submit(self, payload: dict[str, Any]) -> TracesNTResponse:
        token = await self._token()
        async with self._client() as client:
            resp = await client.post(
                "/dds/v1/statements",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            if resp.status_code >= 500:
                raise TracesNTError(f"upstream 5xx: {resp.status_code}")
            if resp.status_code >= 400:
                # 4xx is a client error, no retry; surface to caller.
                log.warning(
                    "traces_nt.submit.rejected",
                    status=resp.status_code,
                    body=resp.text[:500],
                )
                raise TracesNTError(
                    f"DDS rejected by TRACES NT: {resp.status_code} {resp.text[:200]}",
                )
            data = resp.json()
            return TracesNTResponse(
                reference=str(data["reference_number"]),
                verification_number=data.get("verification_number"),
                raw=data,
            )
