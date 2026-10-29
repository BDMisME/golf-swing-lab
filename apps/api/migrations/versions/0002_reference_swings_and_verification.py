"""Add ReferenceSwing verification and category fields

Revision ID: 0002_reference_swings
Revises: 0001_initial
Create Date: 2026-10-29 00:27:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_reference_swings"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "reference_swings" not in tables:
        op.create_table(
            "reference_swings",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("club_type", sa.String(32), nullable=False, index=True),
            sa.Column("handedness", sa.String(16), nullable=False, server_default="right"),
            sa.Column("camera_angle", sa.String(16), nullable=False, server_default="DTL"),
            sa.Column("shot_type", sa.String(32), nullable=False, server_default="full_swing"),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("reference_author", sa.String(120), nullable=False, server_default=""),
            sa.Column("source_url", sa.String(512), nullable=False, server_default=""),
            sa.Column("content_license", sa.String(120), nullable=False, server_default=""),
            sa.Column("storage_key", sa.String(512), nullable=False, server_default=""),
            sa.Column("thumbnail_url", sa.String(512), nullable=True),
            sa.Column("verified_club", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("verified_camera_angle", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("analysis_status", sa.String(32), nullable=False, server_default="pending_analysis"),
            sa.Column("reference_category", sa.String(32), nullable=False, server_default="test_fixture"),
            sa.Column("is_verified_standard", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("verification_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_type", sa.String(32), nullable=False, server_default="local_fixture"),
            sa.Column("fps", sa.Float(), nullable=False, server_default="30.0"),
            sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.String(64), nullable=False, server_default=""),
            sa.Column("event_timestamps", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("pose_artifact", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("calibration_params", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("analysis_version", sa.String(32), nullable=False, server_default="pose-v1"),
            sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_ref_swings_club_hand",
            "reference_swings",
            ["club_type", "handedness", "is_default"],
        )
    else:
        columns = [c["name"] for c in inspector.get_columns("reference_swings")]
        if "reference_category" not in columns:
            op.add_column(
                "reference_swings",
                sa.Column("reference_category", sa.String(32), nullable=False, server_default="test_fixture"),
            )
        if "is_verified_standard" not in columns:
            op.add_column(
                "reference_swings",
                sa.Column("is_verified_standard", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        if "verification_notes" not in columns:
            op.add_column(
                "reference_swings",
                sa.Column("verification_notes", sa.Text(), nullable=False, server_default=""),
            )
        if "source_type" not in columns:
            op.add_column(
                "reference_swings",
                sa.Column("source_type", sa.String(32), nullable=False, server_default="local_fixture"),
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "reference_swings" in tables:
        columns = [c["name"] for c in inspector.get_columns("reference_swings")]
        for col in ["source_type", "verification_notes", "is_verified_standard", "reference_category"]:
            if col in columns:
                op.drop_column("reference_swings", col)
