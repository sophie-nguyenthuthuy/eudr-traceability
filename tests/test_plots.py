from __future__ import annotations


async def test_create_polygon_plot(client, admin_org, auth_header) -> None:
    body = {
        "producer_org_id": str(admin_org.id),
        "commodity": "coffee",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [108.0500, 12.6667],
                    [108.0510, 12.6667],
                    [108.0510, 12.6677],
                    [108.0500, 12.6677],
                    [108.0500, 12.6667],
                ],
            ],
        },
        "planted_year": 2015,
    }
    resp = await client.post("/api/v1/plots", json=body, headers=auth_header)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["geolocation_type"] == "polygon"
    assert data["area_ha"] > 0
    assert data["commodity"] == "coffee"


async def test_point_plot_requires_area(client, admin_org, auth_header) -> None:
    body = {
        "producer_org_id": str(admin_org.id),
        "commodity": "coffee",
        "geometry": {"type": "Point", "coordinates": [108.05, 12.66]},
    }
    resp = await client.post("/api/v1/plots", json=body, headers=auth_header)
    assert resp.status_code == 422
    assert "declared holding area" in resp.json()["detail"]


async def test_point_plot_under_4ha_ok(client, admin_org, auth_header) -> None:
    body = {
        "producer_org_id": str(admin_org.id),
        "commodity": "coffee",
        "geometry": {"type": "Point", "coordinates": [108.05, 12.66]},
        "declared_area_ha": 2.5,
    }
    resp = await client.post("/api/v1/plots", json=body, headers=auth_header)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["geolocation_type"] == "point"
    assert data["area_ha"] == 2.5
