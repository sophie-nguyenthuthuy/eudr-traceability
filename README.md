# EUDR Traceability

Production-grade traceability backend for Vietnamese coffee, rubber, and wood producers exporting to the European Union under the **EU Deforestation Regulation (EUDR, Regulation (EU) 2023/1115)**.

EUDR enforcement starts **30 December 2025** for large operators and **30 June 2026** for SMEs. Operators placing relevant commodities on the EU market must submit a **Due Diligence Statement (DDS)** to the EU TRACES NT information system, including the **geolocation of every plot of land** where the commodity was produced and proof that no deforestation has occurred after the **2020-12-31 cutoff**.

Vietnam exports ~1.6M tonnes of coffee annually, the majority to the EU. Falling out of compliance means goods are turned away at port. This service is the system of record producers and exporters need to stay in.

## What this service does

- **Plot registry** — register each producer plot with a polygon (or point for ≤4ha holdings), commodity, planted year, and ownership proof. Geometries are validated against EUDR Annex requirements and stored in PostGIS.
- **Deforestation check** — overlap every plot polygon against the Hansen / Global Forest Change tree-cover-loss raster after the 2020-12-31 cutoff, plus optional JRC TMF and national forest map layers. Each plot gets a risk score and is gated for shipment use.
- **Chain of custody** — record every transformation (drying, hulling, milling, processing) and custody transfer (farmer → cooperative → processor → exporter) as an immutable, signed event chain. Lots can be split and merged with quantities preserved.
- **Due Diligence Statement builder** — assembles the DDS payload per the EU TRACES NT schema for a shipment, links it to the precise plots, harvests, and custody events, and submits it asynchronously. Stores the TRACES reference number returned by the EU.
- **Audit log** — every state-changing API call is appended to an immutable audit log keyed by user, organization, and request hash.

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌─────────────────────┐
│ Mobile / Web │───▶│ FastAPI API  │───▶│ PostgreSQL + PostGIS│
└──────────────┘    └──────┬───────┘    └─────────────────────┘
                           │
                           ▼
                    ┌──────────────┐    ┌─────────────────────┐
                    │ Celery worker│───▶│ EU TRACES NT API    │
                    └──────┬───────┘    └─────────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Hansen GFC   │
                    │ raster (S3)  │
                    └──────────────┘
```

- **API**: FastAPI, JWT (RS256) auth, role-based access (`producer`, `cooperative`, `exporter`, `auditor`, `admin`).
- **DB**: PostgreSQL 16 + PostGIS 3.4. Migrations via Alembic. Geometries stored in EPSG:4326.
- **Worker**: Celery on Redis. Handles deforestation checks and TRACES NT submission with retry/backoff.
- **Object storage**: S3-compatible (MinIO locally) for ownership-proof scans and DDS payloads.
- **Observability**: structured JSON logs (structlog), OpenTelemetry exporters wired in `eudr.logging_config`.

## Quick start (local)

```bash
cp .env.example .env
make up            # postgres + postgis + redis + minio + api + worker
make migrate       # alembic upgrade head
make seed          # demo coop + 3 plots in Đắk Lắk + 1 lot
make test          # pytest with testcontainers
```

API docs at `http://localhost:8000/docs`. MinIO console at `http://localhost:9001`.

## EUDR compliance notes

- **Cutoff date**: 2020-12-31 (Art. 2(13)). Plots with tree-cover loss after this date are rejected for shipments.
- **Geolocation precision** (Art. 9(1)(d)):
  - Holdings ≤ 4 ha: a single latitude/longitude point is accepted.
  - Holdings > 4 ha: a polygon with sufficient vertices to delineate the plot.
- **Commodities covered**: coffee (HS 0901), natural rubber (HS 4001), wood and wood products (HS 44xx). Cocoa, oil palm, soy, cattle, and their derivatives are also in scope of the regulation but out of scope of this codebase.
- **DDS retention**: 5 years from submission (Art. 5(3)). We never delete a submitted DDS — soft-delete only.
- **TRACES NT** is the EU Commission's information system that receives DDS submissions. The integration in `eudr.services.traces_nt` posts to the sandbox by default; flip `TRACES_NT_ENV=production` for the live endpoint.

## License

Apache 2.0. See [LICENSE](LICENSE).
