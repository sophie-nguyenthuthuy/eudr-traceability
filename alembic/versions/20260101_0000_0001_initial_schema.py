"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00

Creates the complete schema: PostGIS extension, enum types, all tables,
spatial indexes, and foreign keys.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    org_type = sa.Enum(
        "producer", "cooperative", "processor", "exporter", "auditor",
        name="organization_type",
    )
    user_role = sa.Enum(
        "producer", "cooperative_officer", "exporter", "auditor", "admin",
        name="user_role",
    )
    commodity = sa.Enum("coffee", "rubber", "wood", name="commodity")
    geolocation_type = sa.Enum("point", "polygon", name="geolocation_type")
    lot_status = sa.Enum(
        "draft", "sealed", "dds_pending", "dds_submitted", "shipped", "rejected",
        name="lot_status",
    )
    custody_event_type = sa.Enum(
        "transfer", "transformation", "transport", "split", "merge", "inspection",
        name="custody_event_type",
    )
    dds_status = sa.Enum(
        "draft", "ready", "submitted", "accepted", "rejected", "withdrawn",
        name="dds_status",
    )
    deforestation_source = sa.Enum(
        "hansen_gfc", "jrc_tmf", "national_forest_map", "manual",
        name="deforestation_source",
    )
    for enum in (
        org_type, user_role, commodity, geolocation_type, lot_status,
        custody_event_type, dds_status, deforestation_source,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", org_type, nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("address", sa.String(1024)),
        sa.Column("tax_id", sa.String(64)),
        sa.Column("eori_number", sa.String(64)),
    )
    op.create_index("ix_organizations_type", "organizations", ["type"])
    op.create_index("ix_organizations_tax_id", "organizations", ["tax_id"])
    op.create_index("ix_organizations_eori_number", "organizations", ["eori_number"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", user_role, nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "plots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "producer_org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_ref", sa.String(128)),
        sa.Column("commodity", commodity, nullable=False),
        sa.Column("geolocation_type", geolocation_type, nullable=False),
        sa.Column(
            "geometry",
            Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("area_ha", sa.Numeric(12, 4), nullable=False),
        sa.Column("planted_year", sa.SmallInteger),
        sa.Column("ownership_proof_url", sa.String(1024)),
        sa.Column("cutoff_compliant", sa.Boolean),
        sa.Column("notes", sa.String(2048)),
        sa.CheckConstraint("area_ha > 0", name="plots_area_positive"),
        sa.CheckConstraint(
            "(geolocation_type = 'point' AND area_ha <= 4) OR geolocation_type = 'polygon'",
            name="plots_point_only_for_small_holdings",
        ),
    )
    op.create_index("ix_plots_producer_org_id", "plots", ["producer_org_id"])
    op.create_index("ix_plots_external_ref", "plots", ["external_ref"])
    op.create_index("ix_plots_commodity", "plots", ["commodity"])
    op.execute("CREATE INDEX plots_geom_gix ON plots USING GIST (geometry)")

    op.create_table(
        "harvests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "plot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity_kg", sa.Numeric(14, 3), nullable=False),
        sa.Column("harvest_date", sa.Date, nullable=False),
        sa.Column("external_ref", sa.String(128)),
        sa.CheckConstraint("quantity_kg > 0", name="harvests_quantity_positive"),
    )
    op.create_index("ix_harvests_plot_id", "harvests", ["plot_id"])
    op.create_index("ix_harvests_harvest_date", "harvests", ["harvest_date"])
    op.create_index("ix_harvests_external_ref", "harvests", ["external_ref"])

    op.create_table(
        "lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lot_code", sa.String(64), nullable=False),
        sa.Column("commodity", commodity, nullable=False),
        sa.Column("hs_code", sa.String(10), nullable=False),
        sa.Column("total_quantity_kg", sa.Numeric(14, 3), nullable=False),
        sa.Column("status", lot_status, nullable=False, server_default="draft"),
        sa.Column(
            "current_holder_org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("lot_code", name="lots_lot_code_unique"),
        sa.CheckConstraint("total_quantity_kg > 0", name="lots_quantity_positive"),
    )
    op.create_index("ix_lots_commodity", "lots", ["commodity"])
    op.create_index("ix_lots_status", "lots", ["status"])
    op.create_index("ix_lots_current_holder_org_id", "lots", ["current_holder_org_id"])

    op.create_table(
        "lot_compositions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "lot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "harvest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("harvests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity_kg", sa.Numeric(14, 3), nullable=False),
        sa.UniqueConstraint("lot_id", "harvest_id", name="lot_compositions_unique"),
        sa.CheckConstraint("quantity_kg > 0", name="lot_compositions_quantity_positive"),
    )
    op.create_index("ix_lot_compositions_lot_id", "lot_compositions", ["lot_id"])
    op.create_index("ix_lot_compositions_harvest_id", "lot_compositions", ["harvest_id"])

    op.create_table(
        "custody_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "lot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", custody_event_type, nullable=False),
        sa.Column(
            "from_org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "to_org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "location",
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        ),
        sa.Column("document_url", sa.String(1024)),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("prev_hash", sa.String(128)),
        sa.Column("event_hash", sa.String(128), nullable=False),
        sa.Column("signature", sa.String(512)),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_index("ix_custody_events_lot_id", "custody_events", ["lot_id"])
    op.create_index("ix_custody_events_from_org_id", "custody_events", ["from_org_id"])
    op.create_index("ix_custody_events_to_org_id", "custody_events", ["to_org_id"])
    op.create_index("ix_custody_events_prev_hash", "custody_events", ["prev_hash"])
    op.create_index("ix_custody_events_event_hash", "custody_events", ["event_hash"])
    op.create_index(
        "custody_events_lot_occurred_at_idx",
        "custody_events",
        ["lot_id", "occurred_at"],
    )

    op.create_table(
        "due_diligence_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "lot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "operator_org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dds_reference", sa.String(64), nullable=False),
        sa.Column("status", dds_status, nullable=False, server_default="draft"),
        sa.Column("traces_nt_reference", sa.String(64), unique=True),
        sa.Column("traces_nt_verification_number", sa.String(64)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.String(2048)),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("risk_assessment", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("mitigation_measures", sa.String(4096)),
        sa.UniqueConstraint("dds_reference", name="dds_reference_unique"),
    )
    op.create_index("ix_dds_lot_id", "due_diligence_statements", ["lot_id"])
    op.create_index("ix_dds_operator_org_id", "due_diligence_statements", ["operator_org_id"])
    op.create_index("ix_dds_status", "due_diligence_statements", ["status"])

    op.create_table(
        "deforestation_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "plot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", deforestation_source, nullable=False),
        sa.Column("cutoff_date", sa.Date, nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overlap_ha", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("risk_score", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(2048)),
        sa.Column("raw_result", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_deforestation_checks_plot_id", "deforestation_checks", ["plot_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "actor_org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
        ),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64)),
        sa.Column("request_hash", sa.String(128)),
        sa.Column("payload_diff", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_actor_org_id", "audit_logs", ["actor_org_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])


def downgrade() -> None:
    for tbl in (
        "audit_logs",
        "deforestation_checks",
        "due_diligence_statements",
        "custody_events",
        "lot_compositions",
        "lots",
        "harvests",
        "plots",
        "users",
        "organizations",
    ):
        op.drop_table(tbl)
    for enum_name in (
        "deforestation_source",
        "dds_status",
        "custody_event_type",
        "lot_status",
        "geolocation_type",
        "commodity",
        "user_role",
        "organization_type",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
