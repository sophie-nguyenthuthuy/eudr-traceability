"""Tests for the TRACES NT HTTP client.

We never hit the real EU endpoint. Instead we pass an ``httpx.MockTransport``
into the client and assert on the request shape and the parsed response.
"""

from __future__ import annotations

import json

import httpx
import pytest

from eudr.errors import TracesNTError
from eudr.services.traces_nt import TracesNTClient


def _stub_settings(client: TracesNTClient) -> None:
    """Inject sandbox credentials so _token() doesn't bail early."""
    client.settings = client.settings.model_copy(
        update={
            "traces_nt_base_url": "https://traces.test",
            "traces_nt_client_id": "test-client",
            "traces_nt_client_secret": "test-secret",
        },
    )


def _build_transport(
    *, token_status: int = 200, dds_status: int = 200
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/oauth2/token":
            if token_status != 200:
                return httpx.Response(token_status, text="auth failed")
            return httpx.Response(
                200,
                json={"access_token": "fake-bearer-token", "expires_in": 3600},
            )
        if request.url.path == "/dds/v1/statements":
            if dds_status >= 500:
                return httpx.Response(dds_status, text="upstream error")
            if dds_status >= 400:
                return httpx.Response(
                    dds_status,
                    json={"error": "validation_failed", "details": ["bad geometry"]},
                )
            return httpx.Response(
                200,
                json={
                    "reference_number": "TNT-2026-00042",
                    "verification_number": "VER-XYZ-123",
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler), captured


async def test_submit_happy_path() -> None:
    transport, captured = _build_transport()
    client = TracesNTClient(transport=transport)
    _stub_settings(client)

    resp = await client.submit({"lot": {"id": "abc"}})

    assert resp.reference == "TNT-2026-00042"
    assert resp.verification_number == "VER-XYZ-123"
    # Two calls: OAuth then DDS submit
    assert [r.url.path for r in captured] == ["/oauth2/token", "/dds/v1/statements"]
    # Bearer token from the OAuth response is attached
    assert captured[1].headers["authorization"] == "Bearer fake-bearer-token"
    # The body we passed is forwarded verbatim
    assert json.loads(captured[1].content)["lot"]["id"] == "abc"


async def test_submit_4xx_surfaces_immediately() -> None:
    """4xx is a client error — must NOT be retried, must raise TracesNTError."""
    transport, captured = _build_transport(dds_status=422)
    client = TracesNTClient(transport=transport)
    _stub_settings(client)

    with pytest.raises(TracesNTError) as exc:
        await client.submit({"lot": {"id": "abc"}})
    assert "422" in str(exc.value)
    # One oauth + one (non-retried) submit
    submit_calls = [r for r in captured if r.url.path == "/dds/v1/statements"]
    assert len(submit_calls) == 1


async def test_submit_missing_credentials_errors() -> None:
    transport, _ = _build_transport()
    client = TracesNTClient(transport=transport)
    # don't stub settings — credentials remain None
    with pytest.raises(TracesNTError, match="credentials not configured"):
        await client.submit({"lot": {"id": "abc"}})
